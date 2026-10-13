"""AMVO command-line interface. Offline unless a command is explicitly given --network; no model API calls."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from datetime import datetime, timezone
from urllib.parse import urlsplit

from .core import RecordError, audit_public, canonical_bytes, list_records, report
from .lineage import EVENT_TYPES, ledger_head, lineage, load_events, next_event, write_event
from .provenance import FixtureFetcher, LiveFetcher, pin_state, replay_pin, write_capture
from .registry import (LAYERS, OBJECT_SCHEMA, canonical_url, check_registry, load_registry, locate, migrate,
                       ref, registry_report, slug, validate_object, write_manifest, write_object)

ROOT = Path(__file__).resolve().parent.parent


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(payload) + b"\n")


REF_FIELDS = ("source", "revision", "claim", "formal_target")
REF_LISTS = ("parent_claims", "claims", "evidence")


def _from_draft(draft: object, objects: dict) -> dict:
    """a registry object from a draft whose references are bare ids; the ids of sources and
    pinned revisions are derived when left out, every other object names its own id"""
    if not isinstance(draft, dict) or draft.get("kind") not in LAYERS:
        raise RecordError("a draft is a JSON object with a known kind")
    obj = dict(draft, object_schema=OBJECT_SCHEMA)

    def resolve(oid: object) -> dict:
        if not isinstance(oid, str) or oid not in objects:
            raise RecordError(f"draft refers to {oid!r}, which is not registered")
        return ref(objects[oid])
    for field in REF_FIELDS:
        if field in obj and obj["kind"] != field:
            obj[field] = resolve(obj[field])
    for field in REF_LISTS:
        if isinstance(obj.get(field), list):
            obj[field] = [resolve(x) for x in obj[field]]
    if obj["kind"] == "source" and isinstance(obj.get("canonical_url"), str):
        obj["canonical_url"] = canonical_url(obj["canonical_url"])
        if "id" not in obj:
            parts = urlsplit(obj["canonical_url"])
            obj["id"] = "amvo-src-" + slug((parts.hostname or "") + parts.path)
    if "id" not in obj and obj["kind"] == "revision" and isinstance(obj.get("pin"), dict):
        obj["id"] = ("amvo-rev-" + slug(obj["source"]["id"].removeprefix("amvo-src-"), 40) + "-"
                     + slug(str(obj["pin"].get("value")), 16))
    return validate_object(obj)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="amvo", description="AMVO verifier (offline by default)")
    parser.add_argument("command", choices=["validate", "verify", "build-site", "audit-public", "replay-pins",
                                            "record-event", "migrate", "registry-report", "locate", "register"])
    parser.add_argument("--cases", type=Path, default=ROOT / "cases")
    parser.add_argument("--root", type=Path, default=ROOT, help="project root holding evidence/")
    parser.add_argument("--events", type=Path, help="event ledger directory (default: <root>/events)")
    parser.add_argument("--registry", type=Path, help="v0.2 registry directory (default: <root>/registry)")
    parser.add_argument("--query", help="locate: a source URL, a pin value, or a registry id")
    parser.add_argument("--draft", type=Path, help="register: a JSON draft of one registry object")
    parser.add_argument("--output", type=Path, help="report JSON file or generated site directory")
    parser.add_argument("--network", action="store_true",
                        help="replay-pins only: allow live, allowlisted HTTPS fetches")
    parser.add_argument("--fixtures", type=Path, help="replay-pins only: canned responses (tests)")
    parser.add_argument("--case", action="append", default=[], help="replay-pins only: limit to these ids")
    parser.add_argument("--type", choices=EVENT_TYPES, help="record-event: the event type")
    parser.add_argument("--target", help="record-event: the record the event is about")
    parser.add_argument("--by", help="record-event supersedes: the newer record")
    parser.add_argument("--source-url", help="record-event: public evidence for the event")
    parser.add_argument("--rationale", help="record-event: why, in one or two sentences")
    parser.add_argument("--recorded-by", help="record-event: who records it (a role, not a private name)")
    args = parser.parse_args(argv)
    events_dir = args.events or (args.root / "events")
    registry_dir = args.registry or (args.root / "registry")
    try:
        records = list_records(args.cases)
        events = load_events(events_dir)
        objects, manifests = load_registry(registry_dir)
        index = check_registry(objects, manifests, records)
        lineages = lineage(records + [objects[k] for k in sorted(objects)], events)
        if args.command == "validate":
            layers = ", ".join(f"{len(index[k])} {LAYERS[k][0]}" for k in LAYERS)
            print(f"VALID: {len(records)} public records, {len(events)} events; registry v0.2: {layers}, "
                  f"{len(manifests)} migrated records")
            return 0
        if args.command == "migrate":
            new_objects, new_manifests = migrate(records, objects, manifests)
            merged = dict(objects, **{o["id"]: o for o in new_objects})
            check_registry(merged, dict(manifests, **{m["case_id"]: m for m in new_manifests}), records)
            for obj in new_objects:
                write_object(registry_dir, obj)
            for m in new_manifests:
                write_manifest(registry_dir, m)
                print(f"MIGRATED: {m['case_id']} -> " + ", ".join(o["id"] for o in m["objects"]))
            print(f"MIGRATION: {len(new_manifests)} records, {len(new_objects)} new objects")
            return 0
        if args.command == "locate":
            if not args.query:
                print("AMVO ERROR: locate needs --query", file=sys.stderr)
                return 2
            found = locate(objects, args.query)
            print(json.dumps(found, ensure_ascii=False, indent=2))
            return 0 if found["sources"] else 1
        if args.command == "register":
            if not args.draft:
                print("AMVO ERROR: register needs --draft FILE", file=sys.stderr)
                return 2
            obj = _from_draft(json.loads(args.draft.read_text(encoding="utf-8")), objects)
            check_registry(dict(objects, **{obj["id"]: obj}), manifests, records)
            path, created = write_object(registry_dir, obj)
            state = "REGISTERED" if created else "UNCHANGED"
            print(f"{state}: {obj['id']} -> {path.relative_to(registry_dir).as_posix()}")
            return 0
        if args.command == "record-event":
            missing = [name for name in ("type", "target", "rationale", "recorded_by") if not getattr(args, name)]
            if missing:
                print("AMVO ERROR: record-event needs " + ", ".join("--" + m.replace("_", "-") for m in missing),
                      file=sys.stderr)
                return 2
            now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
            event = next_event(records, events, args.type, args.target, rationale=args.rationale,
                               recorded_by=args.recorded_by, recorded_at=now, source_url=args.source_url,
                               by=args.by)
            path = write_event(events_dir, event)
            print(f"RECORDED: {event['event_id']} {event['type']} {event['target']} -> {path.name}")
            return 0
        if args.command == "audit-public":
            findings = audit_public(records, events, [objects[k] for k in sorted(objects)])
            for finding in findings:
                print(f"REVIEW REQUIRED: {finding}")
            if findings:
                return 1
            print(f"PUBLIC GATE: {len(records)} records passed basic screening")
            return 0
        if args.command == "replay-pins":
            if args.network == bool(args.fixtures):
                print("AMVO ERROR: replay-pins needs exactly one of --network (live) or --fixtures DIR",
                      file=sys.stderr)
                return 2
            chosen = [r for r in records if "pin" in r["source"] and (not args.case or r["id"] in args.case)]
            worst = 0
            for rec in chosen:
                fetch = LiveFetcher() if args.network else FixtureFetcher(args.fixtures)
                capture = replay_pin(rec, fetch)
                path = write_capture(args.root, capture)
                print(f"{capture['status'].upper()}: {rec['id']} {capture['pin']['kind']} "
                      f"{capture['pin']['value'][:12]} -> {path.relative_to(args.root).as_posix()}")
                if capture["status"] in ("mismatch", "not_found"):
                    worst = 1
            print(f"REPLAYED: {len(chosen)} declared pins ({'live' if args.network else 'fixture'})")
            return worst
        result = report(records, args.root, pin_state, lineages, ledger_head(events))
        layered = registry_report(objects, manifests, args.root, lineages=lineages, pin_lookup=pin_state)
        if args.command == "registry-report":
            if args.output:
                _write_json(args.output, layered)
            else:
                print(json.dumps(layered, ensure_ascii=False, indent=2))
            return 1 if layered["counts"]["current_claims_checks_not_passed"] else 0
        if args.command == "verify":
            if args.output:
                _write_json(args.output, result)
            else:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            return 1 if any(x["outcome"] == "checks_not_passed" for x in result["cases"]) else 0
        if args.command == "build-site":
            destination = args.output or (ROOT / "site")
            destination.mkdir(parents=True, exist_ok=True)
            for name in ("index.html", "styles.css", "app.js"):
                shutil.copyfile(ROOT / "web" / name, destination / name)
            _write_json(destination / "data" / "index.json",
                        {"records": records, "verification": result, "events": events, "registry": layered,
                         "warning": "This site reports scoped evidence, not global theorem proof."})
            print(f"SITE BUILT: {destination}")
            return 0
    except (RecordError, OSError) as exc:
        print(f"AMVO ERROR: {exc}", file=sys.stderr)
        return 2
    return 2
