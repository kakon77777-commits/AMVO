"""Cloud pilot, part B: Lean formal targets named by the Lean pages of the pilot families of openai/math.

    python tools/intake/openai_math_formal.py --lean DIR     # DIR holds lean/... at the pinned commit, as text
    (add --dry-run to check and report without writing)

Reads tools/intake/openai_math_formal_targets.json: for each pilot family whose CONTENTS.md entry links
lean/docs/NNN.md, the comparator statements that page lists and, for every theorem their comparator
configuration names, the Lean declaration as written. Every file read is checked against its recorded
SHA-256 and git blob id at the pinned commit. Then, for each target: the declaration occurs exactly once in
its Lean file and is followed there by `:=`; the configuration names the theorem and declares the recorded
axioms; the docs page lists the file under the recorded result name; every quoted sentence occurs verbatim
on the page; the toolchain is what lean/lean-toolchain and lean/lake-manifest.json say.

Each target becomes a FormalTarget of its family claim. Nothing is installed, compiled or run: no Lean, no
lake, no comparator. The axiom policy is what the repository declares, not what anything checked, and the
correspondence is the page's own words, not a judgement - so every such claim reads
SEMANTIC_ALIGNMENT_PENDING with formal_kernel not_run. Re-running writes nothing.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from amvo.core import RecordError, list_records, sha256                           # noqa: E402
from amvo.registry import (OBJECT_SCHEMA, check_registry, load_registry, ref,      # noqa: E402
                           slug, validate_object, write_object)

COMMIT = "1581d4cbdd69a0faf34b2089614fe2a814316a6a"
DATA = ROOT / "tools" / "intake" / "openai_math_formal_targets.json"


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def check_target(t: dict, read, toolchain: dict) -> None:
    """raise RecordError unless the recorded target agrees with the files at the pinned commit"""
    lean = read(t["lean_file"]).decode("utf-8")
    stmt = t["exact_statement"]
    if lean.count(stmt) != 1:
        raise RecordError(f"{t['theorem_name']}: the declaration does not occur exactly once in {t['lean_file']}")
    if not lean[lean.index(stmt) + len(stmt):].lstrip(" \n").startswith(":="):
        raise RecordError(f"{t['theorem_name']}: the quoted declaration is not the whole statement (no := after it)")
    keyword, _, rest = stmt.partition(" ")
    declared = rest.split(None, 1)[0] if rest else ""
    if keyword not in ("theorem", "lemma") or not (t["theorem_name"] == declared
                                                   or t["theorem_name"].endswith("." + declared)):
        raise RecordError(f"{t['theorem_name']}: the quoted declaration declares {declared!r}")
    cfg = json.loads(read(t["config"]).decode("utf-8"))
    if t["theorem_name"] not in cfg["theorem_names"]:
        raise RecordError(f"{t['config']} does not name {t['theorem_name']}")
    for field in ("solution_module", "permitted_axioms", "enable_nanoda"):
        if cfg[field] != t[field]:
            raise RecordError(f"{t['config']}: {field} differs from the record")
    doc = read(t["doc"]).decode("utf-8")
    name = t["lean_file"].rsplit("/", 1)[1]
    if f"| {t['result']} | [{name}](../ComparatorChallenges/{name}) |" not in doc:
        raise RecordError(f"{t['doc']} does not list {name} under {t['result']!r}")
    for q in t["doc_quotes"] + [f"[{p}](" for p in t["papers"]]:
        if q not in doc:
            raise RecordError(f"{t['doc']} does not contain the quoted text {q[:40]!r}")
    if read("lean/lean-toolchain").decode("utf-8").strip() != toolchain["lean_toolchain"]:
        raise RecordError("lean/lean-toolchain differs from the record")
    manifest = json.loads(read("lean/lake-manifest.json").decode("utf-8"))
    if [p["rev"] for p in manifest["packages"] if p["name"] == "mathlib"] != [toolchain["mathlib_rev"]]:
        raise RecordError("the Mathlib revision in lean/lake-manifest.json differs from the record")


def target_for(t: dict, data: dict, family: dict) -> dict:
    files, tc = data["files"], data["toolchain"]
    quotes = " ".join(f"“{q}”" for q in t["doc_quotes"])
    correspondence = (
        f"{t['doc']} (SHA-256 {files[t['doc']]['sha256'][:16]}) names as its accompanying paper(s) "
        + "; ".join(f"“{p}”" for p in t["papers"])
        + f", lists the comparator statement {t['lean_file']} (SHA-256 {files[t['lean_file']]['sha256'][:16]}) "
        f"for “{t['result']}”, and says: {quotes} Quoted, not judged: AMVO has not compared this Lean "
        "statement with the family's claims or with the manuscripts.")
    toolchain = (
        f"{tc['lean_toolchain']} (lean/lean-toolchain at commit {COMMIT[:12]}); Mathlib {tc['mathlib_rev']} "
        f"(lean/lake-manifest.json). The repository's comparator setup checks this statement against the solution "
        f"module {t['solution_module']} ({t['config']}; lean/ComparatorChallenges/README.md). The statement is the "
        "declaration as written; definitions it uses are in the same file, fixed by the code pin. AMVO installed "
        "and ran nothing.")
    axiom_policy = (
        f"Declared, not checked: {t['config']} lists permitted_axioms " + ", ".join(t["permitted_axioms"])
        + f" for this theorem (enable_nanoda {str(t['enable_nanoda']).lower()}). AMVO ran no comparator and no Lean "
        "kernel and inspected no proof, so neither the proof nor its axioms are known to AMVO.")
    return validate_object({
        "object_schema": OBJECT_SCHEMA, "kind": "formal_target",
        "id": f"amvo-fmt-openai-math-r{t['family']:03d}-" + slug(t["theorem_name"].removeprefix("OAI."), 90),
        "claim": ref(family), "language": "lean4", "theorem_name": t["theorem_name"],
        "exact_statement": t["exact_statement"], "code_pin": {"kind": "git_commit", "value": COMMIT},
        "toolchain": toolchain, "axiom_policy": axiom_policy, "correspondence": correspondence,
    })


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--lean", type=Path, required=True, help="a directory holding lean/... at the pinned commit")
    parser.add_argument("--data", type=Path, default=DATA)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--dry-run", action="store_true", help="check and report; write nothing")
    args = parser.parse_args(argv)
    try:
        data = json.loads(args.data.read_text(encoding="utf-8"))
        if data["commit"] != COMMIT:
            raise RecordError("the formal-target file names another commit")

        def read(path: str) -> bytes:
            if path not in data["files"]:
                raise RecordError(f"{path} is not among the recorded files")
            body = (args.lean / path).read_bytes()
            want = data["files"][path]
            if sha256(body) != want["sha256"] or git_blob(body) != want["git_blob"]:
                raise RecordError(f"{path} does not match the file at the pinned commit")
            return body

        for path in data["files"]:
            read(path)
        records = list_records(args.root / "cases")
        objects, manifests = load_registry(args.root / "registry")
        fresh, kept = [], 0
        for t in data["targets"]:
            check_target(t, read, data["toolchain"])
            family = objects.get(f"amvo-clm-openai-math-r{t['family']:03d}")
            if family is None or f"Lean: {t['doc']}" not in family.get("location", ""):
                raise RecordError(f"{t['doc']} is not the Lean page of a registered family claim")
            target = target_for(t, data, family)
            old = objects.get(target["id"])
            if old is not None and old != target:
                raise RecordError(f"{target['id']} is registered with different content; objects are never rewritten")
            print(f"CHECKED: {target['id']} ({t['theorem_name']}, {t['lean_file']})")
            if old is None:
                fresh.append(target)
            else:
                kept += 1
        check_registry(dict(objects, **{o["id"]: o for o in fresh}), manifests, records)
        if not args.dry_run:
            for target in fresh:
                write_object(args.root / "registry", target)
        print(f"FORMAL TARGETS: {len(data['targets'])} from {len({t['doc'] for t in data['targets']})} Lean pages; "
              f"{len(fresh)} new, {kept} unchanged" + (" - dry run, nothing written" if args.dry_run else ""))
        return 0
    except (RecordError, OSError, KeyError, ValueError) as exc:
        print(f"AMVO ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
