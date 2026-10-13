"""AMVO command-line interface. Offline unless a command is explicitly given --network; no model API calls."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from datetime import datetime, timezone

from .core import RecordError, audit_public, canonical_bytes, list_records, report
from .lineage import EVENT_TYPES, ledger_head, lineage, load_events, next_event, write_event
from .provenance import FixtureFetcher, LiveFetcher, pin_state, replay_pin, write_capture

ROOT = Path(__file__).resolve().parent.parent


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(payload) + b"\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="amvo", description="AMVO verifier (offline by default)")
    parser.add_argument("command", choices=["validate", "verify", "build-site", "audit-public", "replay-pins",
                                            "record-event"])
    parser.add_argument("--cases", type=Path, default=ROOT / "cases")
    parser.add_argument("--root", type=Path, default=ROOT, help="project root holding evidence/")
    parser.add_argument("--events", type=Path, help="event ledger directory (default: <root>/events)")
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
    try:
        records = list_records(args.cases)
        events = load_events(events_dir)
        lineages = lineage(records, events)
        if args.command == "validate":
            print(f"VALID: {len(records)} public records, {len(events)} events")
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
            findings = audit_public(records, events)
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
                        {"records": records, "verification": result, "events": events,
                         "warning": "This site reports scoped evidence, not global theorem proof."})
            print(f"SITE BUILT: {destination}")
            return 0
    except (RecordError, OSError) as exc:
        print(f"AMVO ERROR: {exc}", file=sys.stderr)
        return 2
    return 2
