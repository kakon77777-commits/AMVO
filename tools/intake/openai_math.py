"""Phase 1 pilot intake: result families of the public openai/math repository, metadata only.

    python tools/intake/openai_math.py --network            # fetch CONTENTS.md at the pin (allowlisted)
    python tools/intake/openai_math.py --contents FILE      # or read a copy, which must hash to the pin's

Reads CONTENTS.md at the already-verified commit, parses the result families, takes a fixed sample
(results 001-003, then every 53rd from 054 to 372 - ten in all, chosen by number, not by content),
and registers each as one Claim on the pinned revision through the registry's own checks. A claim
quotes the repository's own one-paragraph summary (Apache-2.0) and lists the constituent manuscripts
by title and path; no manuscript is copied, and nothing about any claim is checked here - every one
reads NOT_CHECKED. Re-running writes nothing new.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from amvo.core import RecordError, list_records, sha256                           # noqa: E402
from amvo.lineage import load_events                                              # noqa: E402
from amvo.provenance import LiveFetcher                                            # noqa: E402
from amvo.registry import (OBJECT_SCHEMA, check_registry, load_registry, ref,      # noqa: E402
                           validate_object, write_object)

COMMIT = "1581d4cbdd69a0faf34b2089614fe2a814316a6a"
CONTENTS_URL = f"https://raw.githubusercontent.com/openai/math/{COMMIT}/CONTENTS.md"
CONTENTS_SHA256 = "cc7c0b8a1cdedd845a777e77cf682657308503daf8346c1349e06e9259d063c2"
REVISION = "amvo-rev-github-com-openai-math-1581d4cbdd69a0fa"
SAMPLE = (1, 2, 3) + tuple(range(54, 373, 53))
RESULT = re.compile(r"^\*\*(\d{3})\. (.+?)\*\* (.*)$")
# a link, then optionally an annotation such as "— secondary writeup"; a path may contain parentheses
MANUSCRIPT = re.compile(r"^&emsp;\[(.+?)\]\((preprints/\S+?\.pdf)\)(.*)$")
LEAN = re.compile(r"\s*\(\[Lean\]\((lean/docs/\d{3}\.md)\)\)\s*$")
HEADER = re.compile(r"^\*\*(\d+) manuscripts covering (\d+) result families\.\*\*$")


def parse(text: str) -> dict[int, dict]:
    """result number -> {title, summary, lean, manuscripts: [(title, path, note)]}

    Strict: a result or manuscript line that does not parse is an error, not a skip, and the
    counts must equal the ones CONTENTS.md states in its header."""
    results, current, header = {}, None, None
    for number, line in enumerate(text.splitlines(), start=1):
        h = HEADER.match(line)
        if h:
            header = (int(h.group(1)), int(h.group(2)))
            continue
        m = RESULT.match(line)
        if m:
            summary = m.group(3)
            lean = LEAN.search(summary)
            current = {"number": int(m.group(1)), "title": m.group(2).strip(),
                       "summary": LEAN.sub("", summary).strip(), "lean": lean.group(1) if lean else None,
                       "manuscripts": []}
            if current["number"] in results:
                raise RecordError(f"result {m.group(1)} appears twice in CONTENTS.md")
            results[current["number"]] = current
            continue
        if re.match(r"^\*\*\d", line):
            raise RecordError(f"CONTENTS.md line {number}: a result line that does not parse")
        if line.startswith("&emsp;["):
            m = MANUSCRIPT.match(line)
            if m is None or current is None:
                raise RecordError(f"CONTENTS.md line {number}: a manuscript line that does not parse")
            current["manuscripts"].append((m.group(1).strip(), m.group(2), m.group(3).strip()))
    if header is None:
        raise RecordError("CONTENTS.md has no '**N manuscripts covering M result families.**' header")
    found = (sum(len(r["manuscripts"]) for r in results.values()), len(results))
    if found != header:
        raise RecordError(f"CONTENTS.md states {header[0]} manuscripts in {header[1]} families; parsed {found}")
    return results


def claim_for(result: dict, revision: dict) -> dict:
    n = f"{result['number']:03d}"
    listed = [f"{title} ({path})" + (f" {note}" if note else "") for title, path, note in result["manuscripts"]]
    scope = (f"Result family {n} of openai/math as summarised in CONTENTS.md at commit {COMMIT[:12]} "
             f"(CONTENTS.md SHA-256 {CONTENTS_SHA256[:16]}). The precise statements are in its "
             f"{len(listed)} constituent manuscript(s): " + "; ".join(listed) + ". "
             "AMVO has checked nothing about this claim.")
    if len(scope) > 4000:                                  # list as many manuscripts as fit, then count the rest
        keep, used = [], 0
        for item in listed:
            if used + len(item) + 2 > 3000:
                break
            keep.append(item)
            used += len(item) + 2
        scope = (f"Result family {n} of openai/math as summarised in CONTENTS.md at commit {COMMIT[:12]} "
                 f"(CONTENTS.md SHA-256 {CONTENTS_SHA256[:16]}). The precise statements are in its "
                 f"{len(listed)} constituent manuscripts, among them: " + "; ".join(keep)
                 + f"; and {len(listed) - len(keep)} more. AMVO has checked nothing about this claim.")
    location = f"CONTENTS.md result {n}" + (f"; Lean: {result['lean']}" if result["lean"] else "")
    return validate_object({
        "object_schema": OBJECT_SCHEMA, "kind": "claim", "id": f"amvo-clm-openai-math-r{n}",
        "revision": ref(revision), "claim_type": "theorem",
        "statement": f"{result['title']} {result['summary']}",
        "scope": scope, "location": location,
        "attribution": "OpenAI and the contributing authors named in the manuscripts; openai/math, Apache-2.0",
    })


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--network", action="store_true", help="fetch CONTENTS.md at the pin")
    mode.add_argument("--contents", type=Path, help="a local copy of CONTENTS.md at the pin")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    try:
        body = LiveFetcher().get(CONTENTS_URL).body if args.network else args.contents.read_bytes()
        if sha256(body) != CONTENTS_SHA256:
            raise RecordError("CONTENTS.md does not hash to the copy at the pinned commit")
        results = parse(body.decode("utf-8"))
        missing = [n for n in SAMPLE if n not in results]
        if missing:
            raise RecordError(f"sampled results missing from CONTENTS.md: {missing}")
        records = list_records(args.root / "cases")
        objects, manifests = load_registry(args.root / "registry")
        revision = objects.get(REVISION)
        if revision is None:
            raise RecordError(f"{REVISION} is not registered; run python -m amvo migrate first")
        # A claim registered earlier is never rewritten. If today's parse differs from it, the
        # difference must already be on record as a `corrects` event, or the run stops.
        corrected = {ev["target"] for ev in load_events(args.root / "events") if ev["type"] == "corrects"}
        claims = [claim_for(results[n], revision) for n in SAMPLE]
        fresh, kept, unrecorded = [], [], []
        for c in claims:
            old = objects.get(c["id"])
            if old is None:
                fresh.append(c)
            elif old == c:
                kept.append((c, "UNCHANGED"))
            elif c["id"] in corrected:
                kept.append((old, "CORRECTED"))
            else:
                unrecorded.append(c["id"])
        if unrecorded:
            raise RecordError("registered earlier and different from today's parse, with no corrects event: "
                              + ", ".join(unrecorded))
        check_registry(dict(objects, **{c["id"]: c for c in fresh}), manifests, records)
        written = 0
        for c in fresh:
            path, created = write_object(args.root / "registry", c)
            written += created
            print(f"REGISTERED: {c['id']} ({c['location']})")
        for c, state in kept:
            print(f"{state}: {c['id']} ({c['location']})")
        lean = sum(1 for n in SAMPLE if results[n]["lean"])
        print(f"PILOT: {len(claims)} of {len(results)} result families, {written} new, {lean} with a Lean link, "
              f"{sum(len(results[n]['manuscripts']) for n in SAMPLE)} manuscripts listed")
        return 0
    except (RecordError, OSError) as exc:
        print(f"AMVO ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
