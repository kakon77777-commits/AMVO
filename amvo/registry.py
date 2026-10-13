"""P1-C: the layered registry (record format v0.2).

One public result is not one record. A source (a repository, a preprint) has revisions; a
pinned revision states claims; a claim may get formal targets, evidence, reviews and
publications. Each layer is its own immutable object in `registry/<layer>/<id>.json`, and
every reference is `{"id", "sha256"}` — the referent's canonical hash — so no layer can be
changed without every object that relies on it failing to validate:

- evidence cannot rewrite the claim it checks, a review cannot touch the source, and a
  publication can cite only evidence objects, of its own claims;
- nothing stores a verdict: results are computed by the report, never written by hand;
- a claim must name a pinned revision unless its source is synthetic (T06).

Duplicates are refused — one source per canonical URL, one revision per pin, one claim per
statement in a revision, one evidence object per check — and `locate` says where a public
result already lives, so the same result is not filed twice.

v0.1 case files stay where they are, byte for byte. `migrate` maps each one to v0.2 objects
and writes a manifest `registry/migrations/<case-id>.json` that binds the case's canonical
hash to the objects made from it.
"""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from .core import (ENGINE_VERSION, HASH_PATTERN, RIGHTS_MODES, VERIFIER_ID, RecordError, _is_nonempty,
                   _require, _validate_pin, _verify_url, canonical_bytes, check_one, sha256, validate_check)

OBJECT_SCHEMA = "0.2"
REPORT_SCHEMA = "0.2"
LAYERS = {                     # kind: (directory, id prefix)
    "source": ("sources", "src"),
    "revision": ("revisions", "rev"),
    "claim": ("claims", "clm"),
    "formal_target": ("formal_targets", "fmt"),
    "evidence": ("evidence", "evd"),
    "review": ("reviews", "rvw"),
    "publication": ("publications", "pub"),
}
PREFIX_KIND = {prefix: kind for kind, (_, prefix) in LAYERS.items()}
OBJECT_ID = re.compile(r"^amvo-(src|rev|clm|fmt|evd|rvw|pub)-[a-z0-9]+(?:-[a-z0-9]+)*$")
MAX_ID = 120
MAX_OBJECT_BYTES = 256_000
ORIGIN_TYPES = ("repository", "preprint", "paper", "dataset", "synthetic", "other")
CLAIM_TYPES = ("theorem", "lemma", "proposition", "corollary", "conjecture", "computation", "other")
FORMAL_LANGUAGES = ("lean4", "coq", "isabelle", "other")
REVIEWER_CLASSES = ("amvo_maintainer", "independent_mathematician", "original_author", "automated_tool")
AUDIT_STATES = ("in_progress", "objection_raised", "no_objection_in_scope", "needs_revision")
LICENSE_REVIEW = ("pending", "metadata_only", "cleared")
COMMON = {"object_schema", "kind", "id"}
FIELDS = {                     # kind: (required, optional), besides COMMON
    "source": ({"title", "publisher", "authors", "canonical_url", "origin_type", "public", "rights",
                "retrieved_at"}, set()),
    "revision": ({"source", "version_label", "pin", "captured_at"}, set()),
    "claim": ({"revision", "claim_type", "statement", "scope"},
              {"location", "assumptions", "parent_claims", "attribution"}),
    "formal_target": ({"claim", "language", "theorem_name", "exact_statement", "code_pin", "toolchain",
                       "axiom_policy", "correspondence"}, set()),
    "evidence": ({"claim", "check", "bounded_claim"}, {"formal_target"}),
    "review": ({"claim", "reviewer_class", "independence", "conflicts", "scope", "audit_state",
                "references"}, set()),
    "publication": ({"title", "claims", "evidence", "editorial_note", "license_review"}, set()),
}
# claim statuses, from the source and review contract §3; nothing here says VERIFIED
STATUSES = ("NOT_CHECKED", "REPRODUCIBILITY_ONLY", "BOUNDED_PASS", "CHECKS_NOT_PASSED",
            "SEMANTIC_ALIGNMENT_PENDING", "INDEPENDENT_REPLICATION_PENDING", "OBJECTION_OPEN",
            "SUPERSEDED", "WITHDRAWN", "PUBLISHED_REPORT")
BOUNDED = {"rational_sum": "the stated finite rational identity holds exactly",
           "polynomial_coefficients": "the stated coefficient lists are equal once trailing zeros are removed",
           "file_sha256": "the named file's bytes have the stated SHA-256 (artifact integrity only)"}


def object_sha256(obj: dict) -> str:
    return sha256(canonical_bytes(obj))


def ref(obj: dict) -> dict:
    return {"id": obj["id"], "sha256": object_sha256(obj)}


def kind_of(object_id: str) -> str:
    return PREFIX_KIND[object_id.split("-")[1]]


def slug(text: str, limit: int = 60) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:limit].rstrip("-") or "x"


def canonical_url(url: str) -> str:
    """the one spelling a source URL is registered under; arXiv sources are versionless"""
    parts = urlsplit(url)
    host = (parts.hostname or "").lower().removeprefix("www.")
    path = parts.path.rstrip("/")
    if host == "github.com":
        path = path.lower().removesuffix(".git")
        segments = path.split("/")
        path = "/".join(segments[:3]) if len(segments) >= 3 else path
    if host == "arxiv.org":
        path = re.sub(r"^/(?:abs|pdf)/([0-9]{4}\.[0-9]{4,5})(?:v[0-9]+)?(?:\.pdf)?$", r"/abs/\1", path)
    return urlunsplit(("https", host, path, parts.query, ""))


# ---------------------------------------------------------------- shape of one object

def _text(value: object, field: str, limit: int) -> None:
    _require(_is_nonempty(value, limit=limit), f"{field} is required (at most {limit} characters)")


def _date(value: object, field: str) -> None:
    _require(isinstance(value, str), f"{field} must be a date")
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise RecordError(f"invalid {field} date") from exc


def _ref(value: object, kind: str, field: str) -> None:
    _require(isinstance(value, dict) and set(value) == {"id", "sha256"}, f"{field} must be {{id, sha256}}")
    _require(isinstance(value["id"], str) and OBJECT_ID.fullmatch(value["id"]) is not None
             and kind_of(value["id"]) == kind, f"{field} must name a {kind}")
    _require(isinstance(value["sha256"], str) and HASH_PATTERN.fullmatch(value["sha256"]) is not None,
             f"{field}.sha256 must be a 64-hex digest")


def _refs(value: object, kind: str, field: str, *, nonempty: bool) -> None:
    _require(isinstance(value, list) and len(value) <= 256 and (value or not nonempty),
             f"{field} must be a list of {kind} references")
    for item in value:
        _ref(item, kind, field)
    _require(len({item["id"] for item in value}) == len(value), f"{field} repeats a reference")


def _strings(value: object, field: str, limit: int) -> None:
    _require(isinstance(value, list) and len(value) <= 64 and all(_is_nonempty(v, limit=limit) for v in value),
             f"{field} must be a list of short strings")


def validate_object(obj: object) -> dict:
    _require(isinstance(obj, dict), "registry object must be a JSON object")
    kind = obj.get("kind")
    _require(isinstance(kind, str) and kind in LAYERS, "unknown registry object kind")
    required, optional = FIELDS[kind]
    keys = set(obj) - COMMON
    _require(COMMON <= set(obj) and required <= keys <= required | optional,
             f"{kind} fields: missing {sorted((required | COMMON) - set(obj))}, unknown {sorted(keys - required - optional)}")
    _require(obj["object_schema"] == OBJECT_SCHEMA, "unsupported object schema")
    oid = obj["id"]
    _require(isinstance(oid, str) and len(oid) <= MAX_ID and OBJECT_ID.fullmatch(oid) is not None
             and kind_of(oid) == kind, f"{kind} id must be amvo-{LAYERS[kind][1]}-<slug>")
    if kind == "source":
        _text(obj["title"], "title", 1200)
        _text(obj["publisher"], "publisher", 1200)
        _require(isinstance(obj["authors"], list) and obj["authors"]
                 and all(_is_nonempty(a, limit=200) for a in obj["authors"]), "authors must name at least one author")
        _verify_url(obj["canonical_url"])
        _require(obj["canonical_url"] == canonical_url(obj["canonical_url"]),
                 f"canonical_url must be written {canonical_url(obj['canonical_url'])}")
        _require(obj["origin_type"] in ORIGIN_TYPES, "unknown origin_type")
        _require(obj["public"] is True, "only public sources are registered")
        rights = obj["rights"]
        _require(isinstance(rights, dict) and set(rights) == {"mode", "note"} and rights["mode"] in RIGHTS_MODES
                 and _is_nonempty(rights["note"], limit=1200), "rights must be {mode, note}")
        _date(obj["retrieved_at"], "retrieved_at")
    elif kind == "revision":
        _ref(obj["source"], "source", "source")
        _text(obj["version_label"], "version_label", 1200)
        if obj["pin"] is not None:
            _validate_pin(obj["pin"])
        _date(obj["captured_at"], "captured_at")
    elif kind == "claim":
        _ref(obj["revision"], "revision", "revision")
        _require(obj["claim_type"] in CLAIM_TYPES, "unknown claim_type")
        _text(obj["statement"], "statement", 4000)
        _text(obj["scope"], "scope", 4000)
        if "location" in obj:
            _text(obj["location"], "location", 400)
        if "attribution" in obj:
            _text(obj["attribution"], "attribution", 1200)
        if "assumptions" in obj:
            _strings(obj["assumptions"], "assumptions", 1200)
        if "parent_claims" in obj:
            _refs(obj["parent_claims"], "claim", "parent_claims", nonempty=True)
    elif kind == "formal_target":
        _ref(obj["claim"], "claim", "claim")
        _require(obj["language"] in FORMAL_LANGUAGES, "unknown formal language")
        _text(obj["theorem_name"], "theorem_name", 400)
        _text(obj["exact_statement"], "exact_statement", 8000)
        _validate_pin(obj["code_pin"])
        _require(obj["code_pin"]["kind"] in ("git_commit", "sha256"), "code_pin must be a git_commit or sha256")
        for field in ("toolchain", "axiom_policy", "correspondence"):
            _text(obj[field], field, 1200)
    elif kind == "evidence":
        _ref(obj["claim"], "claim", "claim")
        if "formal_target" in obj:
            _ref(obj["formal_target"], "formal_target", "formal_target")
        validate_check(obj["check"])
        _text(obj["bounded_claim"], "bounded_claim", 1200)
    elif kind == "review":
        _ref(obj["claim"], "claim", "claim")
        _require(obj["reviewer_class"] in REVIEWER_CLASSES, "unknown reviewer_class")
        _require(obj["audit_state"] in AUDIT_STATES, "unknown audit_state")
        for field in ("independence", "conflicts", "scope"):
            _text(obj[field], field, 1200)
        _require(isinstance(obj["references"], list) and len(obj["references"]) <= 64, "references must be a list")
        for url in obj["references"]:
            _verify_url(url)
        _require(obj["reviewer_class"] != "independent_mathematician" or obj["references"],
                 "an independent review must cite where it can be read")
    else:
        _text(obj["title"], "title", 1200)
        _refs(obj["claims"], "claim", "claims", nonempty=True)
        _refs(obj["evidence"], "evidence", "evidence", nonempty=False)
        _text(obj["editorial_note"], "editorial_note", 4000)
        _require(obj["license_review"] in LICENSE_REVIEW, "unknown license_review")
    return obj


# ---------------------------------------------------------------- the registry on disk

def load_registry(registry_dir: Path) -> tuple[dict[str, dict], dict[str, dict]]:
    """(objects by id, migration manifests by case id); shapes checked, references not yet"""
    objects, manifests = {}, {}
    if not registry_dir.exists():
        return objects, manifests
    _require(registry_dir.is_dir() and not registry_dir.is_symlink(), "registry path is not a directory")
    known = {d for d, _ in LAYERS.values()} | {"migrations"}
    for sub in sorted(registry_dir.iterdir()):
        if sub.name == "README.md":
            continue
        _require(sub.is_dir() and not sub.is_symlink() and sub.name in known, f"unexpected entry in registry/: {sub.name}")
        for path in sorted(sub.iterdir()):
            _require(path.is_file() and not path.is_symlink() and path.suffix == ".json",
                     f"unexpected file: registry/{sub.name}/{path.name}")
            _require(path.stat().st_size <= MAX_OBJECT_BYTES, f"object exceeds maximum size: {path.name}")
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (UnicodeError, ValueError) as exc:
                raise RecordError(f"invalid UTF-8 JSON: registry/{sub.name}/{path.name}") from exc
            if sub.name == "migrations":
                _validate_manifest(data)
                _require(path.stem == data["case_id"], f"filename and case id differ: {path.name}")
                manifests[data["case_id"]] = data
                continue
            validate_object(data)
            _require(path.stem == data["id"] and LAYERS[data["kind"]][0] == sub.name,
                     f"registry/{sub.name}/{path.name} does not hold its own id and kind")
            _require(data["id"] not in objects, f"duplicate registry id {data['id']}")
            objects[data["id"]] = data
    return objects, manifests


def _validate_manifest(m: object) -> None:
    _require(isinstance(m, dict) and set(m) == {"manifest_schema", "case_id", "record_sha256", "objects",
                                                 "reused", "not_carried"}, "invalid migration manifest")
    _require(m["manifest_schema"] == OBJECT_SCHEMA, "unsupported manifest schema")
    _require(isinstance(m["case_id"], str) and isinstance(m["record_sha256"], str)
             and HASH_PATTERN.fullmatch(m["record_sha256"]) is not None, "manifest must bind a case hash")
    _require(isinstance(m["objects"], list), "manifest objects must be a list")
    for item in m["objects"]:
        _require(isinstance(item, dict) and isinstance(item.get("id"), str)
                 and OBJECT_ID.fullmatch(item["id"]) is not None, "manifest objects are registry references")
        _ref(item, kind_of(item["id"]), "manifest object")
    _require(isinstance(m["reused"], list) and set(m["reused"]) <= {o["id"] for o in m["objects"]},
             "manifest reused ids must be among its objects")
    _strings(m["not_carried"], "not_carried", 600)


def check_registry(objects: dict[str, dict], manifests: dict[str, dict] | None = None,
                   records: list[dict] | None = None) -> dict:
    """references, layering rules and duplicates; returns an index used by the report"""
    def resolve(r: dict, where: str) -> dict:
        target = objects.get(r["id"])
        _require(target is not None, f"{where}: {r['id']} is not registered")
        _require(object_sha256(target) == r["sha256"],
                 f"{where}: {r['id']} changed after it was referenced; register a new object instead of editing")
        return target

    keys: dict[tuple, str] = {}

    def unique(key: tuple, oid: str, what: str) -> None:
        other = keys.setdefault(key, oid)
        _require(other == oid, f"duplicate {what}: {other} and {oid} (register a result once; see `locate`)")

    for oid, obj in sorted(objects.items()):
        kind = obj["kind"]
        if kind == "source":
            unique(("source", obj["canonical_url"]), oid, "source URL")
        elif kind == "revision":
            src = resolve(obj["source"], oid)
            _require(obj["pin"] is not None or src["origin_type"] == "synthetic",
                     f"{oid}: a revision of a real source needs an immutable pin")
            unique(("revision", src["id"], json.dumps(obj["pin"], sort_keys=True) if obj["pin"]
                    else obj["version_label"]), oid, "source revision")
        elif kind == "claim":
            rev = resolve(obj["revision"], oid)
            src = resolve(rev["source"], rev["id"])
            _require(rev["pin"] is not None or src["origin_type"] == "synthetic",
                     f"{oid}: a claim must name a pinned revision (T06)")
            for parent in obj.get("parent_claims", []):
                resolve(parent, oid)
            unique(("claim", rev["id"], " ".join(obj["statement"].split())), oid, "claim statement in this revision")
        elif kind == "formal_target":
            claim = resolve(obj["claim"], oid)
            unique(("formal_target", claim["id"], obj["language"], obj["theorem_name"]), oid, "formal target")
        elif kind == "evidence":
            claim = resolve(obj["claim"], oid)
            if "formal_target" in obj:
                target = resolve(obj["formal_target"], oid)
                _require(target["claim"]["id"] == claim["id"], f"{oid}: formal target belongs to another claim")
            spec = {k: v for k, v in obj["check"].items() if k != "id"}
            unique(("evidence", claim["id"], json.dumps(spec, sort_keys=True)), oid, "check of this claim")
        elif kind == "review":
            resolve(obj["claim"], oid)
        else:
            claim_ids = {resolve(c, oid)["id"] for c in obj["claims"]}
            for e in obj["evidence"]:
                _require(resolve(e, oid)["claim"]["id"] in claim_ids,
                         f"{oid}: cites evidence of a claim it does not report")

    if records is not None:
        record_ids = {r["id"] for r in records}
        clash = record_ids & set(objects)
        _require(not clash, f"v0.1 record and registry object share an id: {sorted(clash)}")
        by_id = {r["id"]: r for r in records}
        for case_id, m in sorted((manifests or {}).items()):
            _require(case_id in by_id, f"migration manifest {case_id}: the v0.1 record is gone (records are kept)")
            _require(m["record_sha256"] == object_sha256(by_id[case_id]),
                     f"migration manifest {case_id}: the v0.1 record changed after migration")
            for item in m["objects"]:
                resolve(item, f"migration manifest {case_id}")

    index = {kind: [] for kind in LAYERS}
    for oid, obj in sorted(objects.items()):
        index[obj["kind"]].append(oid)
    return index


def write_object(registry_dir: Path, obj: dict) -> tuple[Path, bool]:
    """exclusive create; an identical file already there is fine (re-running is idempotent)"""
    folder = registry_dir / LAYERS[obj["kind"]][0]
    return _write_exclusive(folder / (obj["id"] + ".json"), obj)


def write_manifest(registry_dir: Path, manifest: dict) -> tuple[Path, bool]:
    return _write_exclusive(registry_dir / "migrations" / (manifest["case_id"] + ".json"), manifest)


def _write_exclusive(path: Path, payload: dict) -> tuple[Path, bool]:
    data = canonical_bytes(payload) + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as fh:
            fh.write(data)
        return path, True
    except FileExistsError:
        _require(path.read_bytes() == data, f"{path.name} already exists with different content; objects are never overwritten")
        return path, False


# ---------------------------------------------------------------- v0.1 -> v0.2 migration

def _origin(record: dict) -> str:
    if record["type"] == "synthetic_fixture":
        return "synthetic"
    host = (urlsplit(record["source"]["url"]).hostname or "").lower().removeprefix("www.")
    return {"github.com": "repository", "arxiv.org": "preprint"}.get(host, "other")


def _free_id(prefix: str, base: str, objects: dict) -> str:
    """the id `amvo-<prefix>-<base>`, or the first of `-2`, `-3`… still free"""
    n, candidate = 1, f"amvo-{prefix}-{base}"
    while candidate in objects:
        n += 1
        candidate = f"amvo-{prefix}-{base}-{n}"
    return candidate


def migrate(records: list[dict], objects: dict[str, dict], manifests: dict[str, dict]) -> tuple[list[dict], list[dict]]:
    """objects and manifests for every v0.1 record not yet migrated; deterministic, nothing written"""
    objects = dict(objects)
    new_objects, new_manifests = [], []

    def find(kind: str, test) -> dict | None:
        for obj in sorted((o for o in objects.values() if o["kind"] == kind), key=lambda o: o["id"]):
            if test(obj):
                return obj
        return None

    def add(obj: dict) -> dict:
        validate_object(obj)
        _require(obj["id"] not in objects, f"migration would reuse the id {obj['id']} for a different object")
        objects[obj["id"]] = obj
        new_objects.append(obj)
        return obj

    for rec in sorted(records, key=lambda r: r["id"]):
        if rec["id"] in manifests:
            continue
        made, reused, not_carried = [], [], []
        source = rec["source"]
        url = canonical_url(source["url"])
        draft = {"object_schema": OBJECT_SCHEMA, "kind": "source", "title": source["title"],
                 "publisher": source["publisher"], "authors": source["authors"], "canonical_url": url,
                 "origin_type": _origin(rec), "public": True, "rights": rec["rights"],
                 "retrieved_at": source["captured_at"]}
        src = find("source", lambda o: o["canonical_url"] == url)
        if src is None:
            parts = urlsplit(url)
            draft["id"] = _free_id("src", slug(parts.hostname + parts.path), objects)
            src = add(draft)
        else:
            reused.append(src["id"])
            differ = sorted(k for k in draft if k != "id" and draft[k] != src[k])
            if differ:
                not_carried.append(f"source fields kept from {src['id']}, this record differs in: {', '.join(differ)}")
        made.append(src)

        pin = source.get("pin")
        rev = None
        if pin is not None or src["origin_type"] == "synthetic":
            rev = find("revision", lambda o: o["source"]["id"] == src["id"]
                       and (o["pin"] == pin if pin is not None else o["pin"] is None and o["version_label"] == source["version"]))
            if rev is None:
                base = slug(src["id"].removeprefix("amvo-src-"), 40) + "-" + (
                    slug(pin["value"], 16) if pin else slug(source["version"], 24))
                rev = add({"object_schema": OBJECT_SCHEMA, "kind": "revision",
                           "id": _free_id("rev", base, objects), "source": ref(src),
                           "version_label": source["version"], "pin": pin, "captured_at": source["captured_at"]})
            else:
                reused.append(rev["id"])
            made.append(rev)
        else:
            not_carried.append("no revision: the record has no pin and its source is not synthetic")

        if rec["type"] == "public_source_intake":
            not_carried.append("claim text: an intake placeholder, not a claim of the source")
        else:
            case_slug = rec["id"].removeprefix("amvo-")
            claim = add({"object_schema": OBJECT_SCHEMA, "kind": "claim", "id": f"amvo-clm-{case_slug}",
                         "revision": ref(rev), "claim_type": "computation" if src["origin_type"] == "synthetic" else "other",
                         "statement": rec["claim"]["statement"], "scope": rec["claim"]["scope"]})
            made.append(claim)
            for check in rec["checks"]:
                made.append(add({"object_schema": OBJECT_SCHEMA, "kind": "evidence",
                                 "id": f"amvo-evd-{case_slug}-{slug(check['id'], 40)}", "claim": ref(claim),
                                 "check": check, "bounded_claim": BOUNDED[check["kind"]]}))
        if rec["review"]["status"] != "unreviewed":
            not_carried.append(f"review.status {rec['review']['status']}: a status is not a review; "
                               "record a review or an event instead")
        new_manifests.append({"manifest_schema": OBJECT_SCHEMA, "case_id": rec["id"],
                              "record_sha256": object_sha256(rec),
                              "objects": [ref(o) for o in made], "reused": reused, "not_carried": not_carried})
    return new_objects, new_manifests


# ---------------------------------------------------------------- finding where a result lives

def locate(objects: dict[str, dict], query: str) -> dict:
    """the registered source / revisions / claims a URL, pin value or id refers to"""
    q = query.strip()
    hits = []
    if q in objects:
        obj = objects[q]
        while obj["kind"] not in ("source", "revision"):       # climb to the revision it rests on
            up = obj["revision"] if obj["kind"] == "claim" else obj["claims"][0] if obj["kind"] == "publication" else obj["claim"]
            obj = objects[up["id"]]
        hits.append(obj)
    elif q.startswith("https://"):
        url = canonical_url(q)
        hits += [o for o in objects.values() if o["kind"] == "source" and o["canonical_url"] == url]
        m = re.search(r"/(?:abs|pdf)/([0-9]{4}\.[0-9]{4,5}v[0-9]+)", q)
        commit = re.search(r"/commit/([0-9a-f]{40})", q)
        for value in ([m.group(1)] if m else []) + ([commit.group(1)] if commit else []):
            hits += [o for o in objects.values() if o["kind"] == "revision" and o["pin"] and o["pin"]["value"] == value]
    else:
        hits += [o for o in objects.values() if o["kind"] == "revision" and o["pin"]
                 and (o["pin"]["value"] == q or (len(q) >= 7 and o["pin"]["value"].startswith(q)))]
    sources = {o["id"] for o in hits if o["kind"] == "source"}
    sources |= {o["source"]["id"] for o in hits if o["kind"] == "revision"}
    revisions = sorted(o["id"] for o in objects.values() if o["kind"] == "revision" and o["source"]["id"] in sources)
    if any(o["kind"] == "revision" for o in hits):
        revisions = sorted({o["id"] for o in hits if o["kind"] == "revision"})
    claims = sorted(o["id"] for o in objects.values() if o["kind"] == "claim" and o["revision"]["id"] in revisions)
    result = {"query": q, "sources": sorted(sources), "revisions": revisions, "claims": claims}
    if not sources and q.startswith("https://"):
        parts = urlsplit(canonical_url(q))
        result["suggested_source_id"] = "amvo-src-" + slug(parts.hostname + parts.path)
        result["canonical_url"] = canonical_url(q)
    return result


# ---------------------------------------------------------------- the v0.2 report

def _merge_lineage(entries: list[dict]) -> dict:
    out = {"state": "current", "withdrawn_by": None, "superseded_by": None, "corrections": [], "objections": [],
           "events": []}
    for e in entries:
        if e is None:
            continue
        for k in ("corrections", "objections", "events"):
            out[k] += [x for x in e[k] if x not in out[k]]
        out["withdrawn_by"] = out["withdrawn_by"] or e["withdrawn_by"]
        out["superseded_by"] = out["superseded_by"] or e["superseded_by"]
    out["state"] = "withdrawn" if out["withdrawn_by"] else "superseded" if out["superseded_by"] else "current"
    return out


def registry_report(objects: dict[str, dict], manifests: dict[str, dict], project_root: Path, *,
                    lineages: dict | None = None, pin_lookup=None) -> dict:
    """claims with what was actually computed about them, and honest per-layer counts.

    `lineages` is amvo.lineage.lineage over v0.1 records and these objects; a claim inherits its
    v0.1 record's events through the migration manifest, and withdrawal from its revision and
    source. `pin_lookup(pseudo_record, root)` is amvo.provenance.pin_state; a revision's pin is
    checked against captures filed under the revision id or under any v0.1 record it came from.
    """
    lineages = lineages or {}
    legacy: dict[str, list[str]] = {}
    for case_id, m in manifests.items():
        for item in m["objects"]:
            legacy.setdefault(item["id"], []).append(case_id)
    by_kind: dict[str, list[dict]] = {k: [] for k in LAYERS}
    for oid in sorted(objects):
        by_kind[objects[oid]["kind"]].append(objects[oid])

    def lineage_of(oid: str) -> dict:
        return _merge_lineage([lineages.get(oid)] + [lineages.get(c) for c in legacy.get(oid, [])])

    def pin_of(rev: dict) -> dict:
        if rev["pin"] is None:
            return {"status": "no_pin", "verified": False}
        if pin_lookup is None:
            return {"status": "declared_only", "verified": False}
        states = [pin_lookup({"id": sid, "source": {"pin": rev["pin"]}}, project_root)
                  for sid in [rev["id"]] + sorted(legacy.get(rev["id"], []))]
        if any(s["status"] == "capture_invalid" for s in states):
            return {"status": "capture_invalid", "verified": False}
        found = [s for s in states if "captured_at" in s]
        return max(found, key=lambda s: s["captured_at"]) if found else {"status": "declared_only", "verified": False}

    revisions = {}
    for rev in by_kind["revision"]:
        state = pin_of(rev)
        src_lin, rev_lin = lineage_of(rev["source"]["id"]), lineage_of(rev["id"])
        revisions[rev["id"]] = {"id": rev["id"], "source": rev["source"]["id"], "version_label": rev["version_label"],
                                "pin": rev["pin"], "pin_status": state["status"], "pin_verified": state["verified"] is True,
                                "pin_capture": state.get("capture"),
                                "withdrawn": "withdrawn" in (src_lin["state"], rev_lin["state"])}
    claims = []
    for claim in by_kind["claim"]:
        cid, rev = claim["id"], revisions[claim["revision"]["id"]]
        evidence = []
        for e in by_kind["evidence"]:
            if e["claim"]["id"] != cid:
                continue
            try:
                result = check_one(e["check"], project_root)
            except (RecordError, OSError) as exc:
                result = {"id": e["check"]["id"], "kind": e["check"]["kind"], "result": "error", "scope": str(exc)}
            evidence.append({"id": e["id"], "kind": e["check"]["kind"], "result": result["result"],
                             "bounded_claim": e["bounded_claim"]})
        formal = [f["id"] for f in by_kind["formal_target"] if f["claim"]["id"] == cid]
        reviews = [{"id": r["id"], "reviewer_class": r["reviewer_class"], "audit_state": r["audit_state"]}
                   for r in by_kind["review"] if r["claim"]["id"] == cid]
        pubs = [p["id"] for p in by_kind["publication"] if any(c["id"] == cid for c in p["claims"])]
        lin = lineage_of(cid)
        if rev["withdrawn"] and lin["state"] != "withdrawn":
            lin = dict(lin, state="withdrawn", withdrawn_by=lin["withdrawn_by"] or "revision or source withdrawn")
        statuses = []
        if lin["state"] == "withdrawn":
            statuses.append("WITHDRAWN")
        elif lin["state"] == "superseded":
            statuses.append("SUPERSEDED")
        if not evidence:
            statuses.append("NOT_CHECKED")
        elif any(e["result"] != "pass" for e in evidence):
            statuses.append("CHECKS_NOT_PASSED")
        elif any(e["kind"] != "file_sha256" for e in evidence):
            statuses.append("BOUNDED_PASS")
        else:
            statuses.append("REPRODUCIBILITY_ONLY")
        if formal:
            statuses.append("SEMANTIC_ALIGNMENT_PENDING")        # no kernel run and no alignment in this engine
        if lin["objections"] or any(r["audit_state"] == "objection_raised" for r in reviews):
            statuses.append("OBJECTION_OPEN")
        if not any(r["reviewer_class"] == "independent_mathematician" and r["audit_state"] == "no_objection_in_scope"
                   for r in reviews):
            statuses.append("INDEPENDENT_REPLICATION_PENDING")
        if pubs:
            statuses.append("PUBLISHED_REPORT")
        claims.append({"id": cid, "claim_type": claim["claim_type"], "statement": claim["statement"],
                       "scope": claim["scope"], "revision": rev["id"], "source": rev["source"],
                       "source_pin": rev["pin"], "source_pin_status": rev["pin_status"],
                       "source_pin_verified": rev["pin_verified"], "evidence": evidence, "formal_targets": formal,
                       "formal_kernel": "not_run", "reviews": reviews, "publications": pubs, "lineage": lin,
                       "legacy_records": sorted(legacy.get(cid, [])), "statuses": statuses, "theorem_proved": False})

    current = [c for c in claims if c["lineage"]["state"] == "current"]
    count = lambda pred, xs: sum(1 for x in xs if pred(x))
    sources = by_kind["source"]
    return {
        "report_schema": REPORT_SCHEMA,
        "engine": VERIFIER_ID,
        "counts": {
            "sources": len(sources),
            "sources_by_origin": {t: n for t in ORIGIN_TYPES if (n := count(lambda s: s["origin_type"] == t, sources))},
            "revisions": len(revisions),
            "revisions_pinned": count(lambda r: r["pin"] is not None, revisions.values()),
            "revisions_pin_verified": count(lambda r: r["pin_verified"], revisions.values()),
            "claims": len(claims),
            "claims_current": len(current),
            "claims_by_type": {t: n for t in CLAIM_TYPES if (n := count(lambda c: c["claim_type"] == t, claims))},
            "current_claims_bounded_pass": count(lambda c: "BOUNDED_PASS" in c["statuses"], current),
            "current_claims_not_checked": count(lambda c: "NOT_CHECKED" in c["statuses"], current),
            "current_claims_checks_not_passed": count(lambda c: "CHECKS_NOT_PASSED" in c["statuses"], current),
            "formal_targets": len(by_kind["formal_target"]),
            "formal_kernel_runs": 0,
            "evidence": len(by_kind["evidence"]),
            "reviews": len(by_kind["review"]),
            "publications": len(by_kind["publication"]),
            "theorems_proved": 0,
        },
        "sources": [{"id": s["id"], "title": s["title"], "publisher": s["publisher"], "authors": s["authors"],
                     "canonical_url": s["canonical_url"], "origin_type": s["origin_type"], "rights": s["rights"],
                     "lineage": lineage_of(s["id"])} for s in sources],
        "revisions": list(revisions.values()),
        "claims": claims,
        "disclaimer": (f"AMVO v{ENGINE_VERSION} certifies no external theorem. Counts are per layer: a source is "
                       "not a claim, a claim is not checked until evidence about it is computed, and no formal "
                       "kernel is run by this engine."),
    }
