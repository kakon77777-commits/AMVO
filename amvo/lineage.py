"""P1-B: append-only correction and withdrawal events.

A record is never edited to say it was withdrawn, corrected, replaced or disputed. Instead an
event is appended to `events/`, one canonical JSON file per event, named `ev-<seq>.json`.

- Each event carries the SHA-256 of the record it refers to, as the record stood when the
  event was written. If that record later changes, the ledger no longer validates: a changed
  record has to be published as a new record plus a `supersedes` event.
- Each event carries the SHA-256 of the event before it, so editing or removing an earlier
  event breaks the chain. (Removing the newest event is caught by CI's append-only gate.)
- Event types: `withdraws` (the source withdrew it), `supersedes` (a newer record replaces
  it), `corrects` (an erratum on it), `rebuttal` (a recorded objection or counterexample).
  Closing an objection is not modelled yet, so a recorded objection is never silently closed.

Nothing here changes a record's computed outcome. The report states the outcome and, beside
it, the record's lineage; the dashboard never presents a withdrawn or superseded record as
current.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from .core import RecordError, _is_nonempty, _require, _verify_url, canonical_bytes, sha256

EVENT_SCHEMA = "0.1"
EVENT_TYPES = ("withdraws", "supersedes", "corrects", "rebuttal")
EVENT_NAME = re.compile(r"ev-([0-9]{6})\.json")
RECORDED_AT = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")
GENESIS = "0" * 64
MAX_EVENT_BYTES = 64_000
COMMON = {"event_schema", "seq", "event_id", "type", "target", "target_sha256", "rationale",
          "recorded_by", "recorded_at", "prev_sha256"}
FIELDS = {
    "withdraws": COMMON | {"source_url"},
    "corrects": COMMON | {"source_url"},
    "rebuttal": COMMON | {"source_url"},
    "supersedes": COMMON | {"by", "by_sha256"},
}
OPTIONAL = {"supersedes": {"source_url"}}


def event_id(seq: int) -> str:
    return f"ev-{seq:06d}"


def event_sha256(event: dict) -> str:
    return sha256(canonical_bytes(event))


def record_sha256(record: dict) -> str:
    return sha256(canonical_bytes(record))


def _check_shape(event: object) -> dict:
    _require(isinstance(event, dict), "event must be a JSON object")
    kind = event.get("type")
    _require(isinstance(kind, str) and kind in EVENT_TYPES, "unknown event type")
    keys = set(event)
    _require(FIELDS[kind] <= keys <= FIELDS[kind] | OPTIONAL.get(kind, set()),
             f"event fields for {kind}: missing {sorted(FIELDS[kind] - keys)}, "
             f"unknown {sorted(keys - FIELDS[kind] - OPTIONAL.get(kind, set()))}")
    _require(event["event_schema"] == EVENT_SCHEMA, "unsupported event schema")
    _require(type(event["seq"]) is int and event["seq"] >= 1, "event seq must be a positive integer")
    _require(event["event_id"] == event_id(event["seq"]), "event_id must be ev-<seq, 6 digits>")
    for field in ("target_sha256", "prev_sha256") + (("by_sha256",) if kind == "supersedes" else ()):
        _require(isinstance(event[field], str) and re.fullmatch(r"[0-9a-f]{64}", event[field]) is not None,
                 f"{field} must be a 64-hex digest")
    _require(_is_nonempty(event["rationale"], limit=1200), "rationale is required")
    _require(_is_nonempty(event["recorded_by"], limit=200), "recorded_by is required")
    _require(isinstance(event["recorded_at"], str) and RECORDED_AT.fullmatch(event["recorded_at"]) is not None,
             "recorded_at must be UTC, YYYY-MM-DDTHH:MM:SSZ")
    try:
        datetime.strptime(event["recorded_at"], "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise RecordError("recorded_at is not a calendar time") from exc
    if "source_url" in event:
        _verify_url(event["source_url"])
    return event


def load_events(events_dir: Path) -> list[dict]:
    """the ledger in seq order; shape and chain checked, records not yet consulted"""
    if not events_dir.exists():
        return []
    _require(events_dir.is_dir() and not events_dir.is_symlink(), "events path is not a directory")
    events = []
    for path in sorted(events_dir.iterdir()):
        if path.name == "README.md":
            continue
        m = EVENT_NAME.fullmatch(path.name)
        _require(m is not None, f"unexpected file in events/: {path.name}")
        _require(path.is_file() and not path.is_symlink(), f"not a regular event file: {path.name}")
        _require(path.stat().st_size <= MAX_EVENT_BYTES, f"event exceeds maximum size: {path.name}")
        try:
            event = json.loads(path.read_text(encoding="utf-8"))
        except (UnicodeError, ValueError) as exc:
            raise RecordError(f"invalid UTF-8 JSON: {path.name}") from exc
        _check_shape(event)
        _require(event["seq"] == int(m.group(1)), f"filename and seq differ: {path.name}")
        events.append(event)
    prev = GENESIS
    for i, event in enumerate(events, start=1):
        _require(event["seq"] == i, f"event ledger has a gap before {event_id(i)}")
        _require(event["prev_sha256"] == prev,
                 f"{event['event_id']}: prev_sha256 does not match the event before it (edited or removed)")
        if i > 1:
            _require(event["recorded_at"] >= events[i - 2]["recorded_at"],
                     f"{event['event_id']}: recorded_at is earlier than the event before it")
        prev = event_sha256(event)
    return events


def lineage(records: list[dict], events: list[dict]) -> dict[str, dict]:
    """each record's lineage; raises if an event no longer matches the records it names"""
    by_id = {r["id"]: r for r in records}
    out = {rid: {"state": "current", "superseded_by": None, "supersedes": [], "withdrawn_by": None,
                 "corrections": [], "objections": [], "events": []} for rid in by_id}
    for ev in events:
        eid, target = ev["event_id"], ev["target"]
        _require(target in by_id, f"{eid}: target record {target!r} does not exist (a record may not be removed)")
        _require(ev["target_sha256"] == record_sha256(by_id[target]),
                 f"{eid}: record {target} changed after this event referred to it; publish a new record "
                 "and a supersedes event instead of editing")
        entry = out[target]
        entry["events"].append(eid)
        if ev["type"] == "withdraws":
            _require(entry["withdrawn_by"] is None, f"{eid}: {target} is already withdrawn")
            entry["withdrawn_by"] = eid
        elif ev["type"] == "corrects":
            entry["corrections"].append(eid)
        elif ev["type"] == "rebuttal":
            entry["objections"].append(eid)
        else:
            newer = ev["by"]
            _require(newer in by_id, f"{eid}: superseding record {newer!r} does not exist")
            _require(newer != target, f"{eid}: a record cannot supersede itself")
            _require(ev["by_sha256"] == record_sha256(by_id[newer]),
                     f"{eid}: record {newer} changed after this event referred to it")
            _require(entry["superseded_by"] is None, f"{eid}: {target} is already superseded")
            seen, cur = {target}, newer
            while cur is not None:                      # following newer versions must not loop back
                _require(cur not in seen, f"{eid}: supersedes chain forms a cycle")
                seen.add(cur)
                cur = out[cur]["superseded_by"]
            entry["superseded_by"] = newer
            out[newer]["supersedes"].append(target)
            out[newer]["events"].append(eid)
    for entry in out.values():
        entry["state"] = ("withdrawn" if entry["withdrawn_by"] else
                          "superseded" if entry["superseded_by"] else "current")
    return out


def ledger_head(events: list[dict]) -> dict:
    return {"events": len(events), "head_sha256": event_sha256(events[-1]) if events else GENESIS}


def next_event(records: list[dict], events: list[dict], kind: str, target: str, *, rationale: str,
               recorded_by: str, recorded_at: str, source_url: str | None = None,
               by: str | None = None) -> dict:
    """the next event for the ledger, checked together with everything already in it"""
    by_id = {r["id"]: r for r in records}
    _require(target in by_id, f"target record {target!r} does not exist")
    seq = len(events) + 1
    event = {"event_schema": EVENT_SCHEMA, "seq": seq, "event_id": event_id(seq), "type": kind,
             "target": target, "target_sha256": record_sha256(by_id[target]), "rationale": rationale,
             "recorded_by": recorded_by, "recorded_at": recorded_at,
             "prev_sha256": event_sha256(events[-1]) if events else GENESIS}
    if kind == "supersedes":
        _require(by in by_id, f"superseding record {by!r} does not exist")
        event.update(by=by, by_sha256=record_sha256(by_id[by]))
    else:
        _require(by is None, "--by is only for supersedes")
    if source_url is not None:
        event["source_url"] = source_url
    _check_shape(event)
    if events:
        _require(recorded_at >= events[-1]["recorded_at"], "recorded_at is earlier than the last event")
    lineage(records, events + [event])
    return event


def write_event(events_dir: Path, event: dict) -> Path:
    events_dir.mkdir(parents=True, exist_ok=True)
    path = events_dir / (event["event_id"] + ".json")
    with path.open("xb") as fh:                         # never overwrite an event
        fh.write(canonical_bytes(event) + b"\n")
    return path
