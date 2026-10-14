"""Cloud pilot, part A: the statements inside the manuscripts of the ten pilot families of openai/math.

    python tools/intake/openai_math_statements.py --pdfs DIR     # DIR holds preprints/... at the pinned commit
    python tools/intake/openai_math_statements.py --texts DIR    # or the texts already extracted, DIR/<path>.txt
    (add --dry-run to check and report without writing)

Reads tools/intake/openai_math_statements.json. For each of the 18 manuscripts it records the PDF's SHA-256,
the SHA-256 of the text that pdftotext -raw extracts from it, and the candidates read from that text: every
numbered theorem, proposition and corollary (no numbered conjecture occurs), with the paper's label, page and
statement. With --pdfs the PDF must hash to the recorded value and pdftotext must be the recorded version;
either way the text must hash to the recorded value.

For every candidate the mechanical check is run and printed: its heading and statement, whitespace normalised,
must occur in the normalised text, beginning and ending on the recorded PDF pages. A paraphrase, a completed
formula or a cleaned-up statement fails it. A candidate that passes and is marked `register` becomes a Claim
on the pinned revision, child of its family claim, through the registry's own checks; a duplicate statement is
refused and the first one kept. A candidate marked `hold` is reported, not registered. Finding a quote shows
that the manuscript states it, not that it is true: every claim reads NOT_CHECKED. Re-running writes nothing.
No manuscript text other than the registered statements is stored, and nothing from the source repository runs.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from amvo.core import RecordError, list_records, sha256                           # noqa: E402
from amvo.lineage import load_events                                              # noqa: E402
from amvo.registry import (OBJECT_SCHEMA, check_registry, load_registry, ref,      # noqa: E402
                           slug, validate_object, write_object)

COMMIT = "1581d4cbdd69a0faf34b2089614fe2a814316a6a"
REVISION = "amvo-rev-github-com-openai-math-1581d4cbdd69a0fa"
DATA = ROOT / "tools" / "intake" / "openai_math_statements.json"
ATTRIBUTION = "OpenAI and the contributing authors named in the manuscripts; openai/math, Apache-2.0"
ABBR = {"theorem": "thm", "proposition": "prop", "corollary": "cor", "conjecture": "conj", "lemma": "lem"}
MAX_STATEMENT = 4000


def normalise(text: str) -> tuple[str, list[int]]:
    """whitespace (str.isspace) collapsed to single spaces and trimmed; with each kept character's original offset"""
    out, where, gap = [], [], False
    for i, ch in enumerate(text):
        if ch.isspace():
            gap = bool(out)
            continue
        if gap:
            out.append(" ")
            where.append(i)
            gap = False
        out.append(ch)
        where.append(i)
    return "".join(out), where


def locate(text: str, heading: str, statement: str) -> list[tuple[int, int]]:
    """(first page, last page) of every occurrence of 'heading statement' in the text; pages split at form feeds"""
    norm, where = normalise(text)
    needle = normalise(heading + " " + statement)[0]
    found, start = [], norm.find(needle)
    while needle and start >= 0:
        a, b = where[start], where[start + len(needle) - 1]
        found.append((1 + text.count("\f", 0, a), 1 + text.count("\f", 0, b)))
        start = norm.find(needle, start + 1)
    return found


def check_candidate(text: str, cand: dict) -> str | None:
    """None when the quote is found verbatim on its recorded pages, else the reason it is not"""
    if cand["statement"] != normalise(cand["statement"])[0] or not cand["statement"]:
        return "the recorded statement is not whitespace-normalised text"
    hits = locate(text, cand["heading"], cand["statement"])
    if not hits:
        return "not found verbatim in the extracted text"
    if (cand["page"], cand["end_page"]) not in hits:
        return f"found, but not on PDF page(s) {cand['page']}-{cand['end_page']} (found on {hits[0][0]}-{hits[0][1]})"
    return None


def claim_id(ms: dict, cand: dict) -> str:
    number = cand["label"].split(" ", 1)[1]
    return f"amvo-clm-openai-math-r{ms['family']:03d}-ms{ms['ms']}-{ABBR[cand['claim_type']]}-{slug(number, 20)}"


def claim_for(ms: dict, cand: dict, extractor: dict, revision: dict, family: dict) -> dict:
    tool = f"{extractor['tool']} {extractor['version']} ({' '.join(extractor['args'])})"
    pages = (f"PDF page {cand['page']}" if cand["page"] == cand["end_page"]
             else f"PDF pages {cand['page']}-{cand['end_page']}")
    label = cand["label"] + (f" ({cand['name']})" if cand["name"] else "")
    scope = (f"{label} of the manuscript “{ms['title']}” ({ms['path']}), one of the manuscripts of result family "
             f"{ms['family']:03d} of openai/math at commit {COMMIT[:12]}. The statement is quoted verbatim from the "
             f"text that {tool} extracts from the PDF (SHA-256 {ms['pdf_sha256'][:16]}), with whitespace "
             f"normalised, and was found there under this heading on {pages}. Text extraction flattens typeset "
             "mathematics (superscripts, subscripts, fractions, large operators, delimiters), so the quote can read "
             "differently from the typeset statement and can carry characters with no Unicode meaning; the PDF is "
             "authoritative.")
    if cand["page"] != cand["end_page"]:
        scope += " The quote crosses a page break and includes whatever the extraction places there, such as a page number."
    scope += (" Finding the quote shows that the manuscript states it, not that it is true. "
              "AMVO has checked nothing about this claim.")
    location = f"{ms['path']}, {cand['label']}, {pages}"
    return validate_object({
        "object_schema": OBJECT_SCHEMA, "kind": "claim", "id": claim_id(ms, cand),
        "revision": ref(revision), "claim_type": cand["claim_type"], "statement": cand["statement"],
        "scope": scope, "location": location, "parent_claims": [ref(family)], "attribution": ATTRIBUTION,
    })


def extract(pdf: Path, extractor: dict) -> bytes:
    version = subprocess.run([extractor["tool"], "-v"], capture_output=True, text=True, check=False)
    found = re.search(r"version (\S+)", version.stdout + version.stderr)
    if not found or found.group(1) != extractor["version"]:
        raise RecordError(f"{extractor['tool']} {extractor['version']} is required "
                          f"(found {found.group(1) if found else 'none'})")
    run = subprocess.run([extractor["tool"], *extractor["args"], str(pdf), "-"], capture_output=True, check=False)
    if run.returncode != 0:
        raise RecordError(f"{extractor['tool']} failed on {pdf.name}")
    return run.stdout


def text_for(ms: dict, args, extractor: dict) -> str:
    if args.pdfs:
        pdf = args.pdfs / ms["path"]
        if sha256(pdf.read_bytes()) != ms["pdf_sha256"]:
            raise RecordError(f"{ms['path']} does not hash to the PDF at the pinned commit")
        data = extract(pdf, extractor)
    else:
        data = (args.texts / (ms["path"].removesuffix(".pdf") + ".txt")).read_bytes()
    if sha256(data) != ms["text_sha256"]:
        raise RecordError(f"the text of {ms['path']} does not hash to the recorded extraction")
    return data.decode("utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--pdfs", type=Path, help="a directory holding preprints/... at the pinned commit")
    mode.add_argument("--texts", type=Path, help="a directory holding the extracted texts, <path>.txt")
    parser.add_argument("--data", type=Path, default=DATA)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--dry-run", action="store_true", help="check and report; write nothing")
    args = parser.parse_args(argv)
    try:
        data = json.loads(args.data.read_text(encoding="utf-8"))
        if data["commit"] != COMMIT:
            raise RecordError("the candidates file names another commit")
        records = list_records(args.root / "cases")
        objects, manifests = load_registry(args.root / "registry")
        revision = objects.get(REVISION)
        if revision is None:
            raise RecordError(f"{REVISION} is not registered")
        taken = {" ".join(o["statement"].split()): o["id"] for o in objects.values()
                 if o["kind"] == "claim" and o["revision"]["id"] == REVISION}
        fresh, kept, report = [], 0, []
        # a family's manuscripts: those its claim lists, and those a recorded `corrects` event adds (r107)
        corrections = {}
        for ev in load_events(args.root / "events"):
            if ev["type"] == "corrects":
                corrections[ev["target"]] = corrections.get(ev["target"], "") + ev["rationale"]
        for ms in data["manuscripts"]:
            family = objects.get(f"amvo-clm-openai-math-r{ms['family']:03d}")
            if family is None or f"({ms['path']})" not in family["scope"] + corrections.get(family["id"], ""):
                raise RecordError(f"{ms['path']} is not a manuscript of a registered family claim")
            text = text_for(ms, args, data["extractor"])
            counts = {"found": len(ms["candidates"]), "kept": 0, "held": 0, "rejected": 0}
            for cand in ms["candidates"]:
                where = f"r{ms['family']:03d} ms{ms['ms']} {cand['label']}"
                reason = check_candidate(text, cand)
                print(f"CHECK {'FOUND' if reason is None else 'FAILED'}: {where} "
                      f"p{cand['page']}-{cand['end_page']}" + (f" ({reason})" if reason else ""))
                if reason is None and len(cand["statement"]) > MAX_STATEMENT:
                    reason = f"statement has {len(cand['statement'])} characters; the registry's limit is {MAX_STATEMENT}"
                if reason is None and cand["decision"] == "hold":
                    counts["held"] += 1
                    report.append(f"HELD: {where}: {cand['hold_reason']}")
                    continue
                first = taken.get(cand["statement"], claim_id(ms, cand))
                if reason is None and first != claim_id(ms, cand):
                    reason = f"duplicate of {first} (the first is kept)"
                if reason is not None:
                    counts["rejected"] += 1
                    report.append(f"REJECTED: {where}: {reason}")
                    continue
                claim = claim_for(ms, cand, data["extractor"], revision, family)
                old = objects.get(claim["id"])
                if old is not None and old != claim:
                    raise RecordError(f"{claim['id']} is registered with different content; claims are never rewritten")
                taken[cand["statement"]] = claim["id"]
                counts["kept"] += 1
                if old is None:
                    fresh.append(claim)
                else:
                    kept += 1
            report.append(f"MANUSCRIPT: r{ms['family']:03d} ms{ms['ms']} {ms['path']}: {counts['found']} found, "
                          f"{counts['kept']} kept, {counts['held']} held, {counts['rejected']} rejected; "
                          f"{ms['lemma_headings_not_taken']} lemma headings not taken")
        check_registry(dict(objects, **{c["id"]: c for c in fresh}), manifests, records)
        if not args.dry_run:
            for claim in fresh:
                write_object(args.root / "registry", claim)
        print("\n".join(report))
        print(f"STATEMENTS: {sum(len(m['candidates']) for m in data['manuscripts'])} candidates in "
              f"{len(data['manuscripts'])} manuscripts; {len(fresh) + kept} kept ({len(fresh)} new, {kept} unchanged)"
              + (" - dry run, nothing written" if args.dry_run else ""))
        return 0
    except (RecordError, OSError, KeyError, ValueError) as exc:
        print(f"AMVO ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
