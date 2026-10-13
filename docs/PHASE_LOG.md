# AMVO phase log

One entry per delivered phase, in the form the Acceptance Matrix (section F) asks for. Each entry
states what was run, on which commit, with what result; nothing here is inferred from a plan.

## P0 — reproducible baseline and safety (v0.1.2)

- **Base:** `a9cf4726597951a33e5c1a831246dc9cf24ca176` (main). Branch `feat/p0-reproducible-baseline`.
- **Baseline found:** 33 tests, 1 error on Windows (`test_symlink_escape_blocked`: creating a
  symlink needs Developer Mode or admin, WinError 1314); CI had run on Linux only and passed.
- **Scope:**
  - `amvo/core.py`: a source host must be a public DNS name or a canonical global IP literal.
    Spellings resolvers accept for local addresses but `ipaddress` does not parse (`127.1`,
    `0x7f000001`, `2130706433`, `0177.0.0.1`, `localhost.`), single-label names and
    `.lan` / `.home.arpa` are refused. One engine version, `0.1.2`, now shared by
    `pyproject.toml`, `amvo.__version__` (was `0.1.0`) and the report's engine id.
  - `schemas/case.schema.json`: brought into line with the runtime — length limits, check-id
    limits, an evidence-path pattern with no empty, `.` or `..` segment, and the rule that a
    `public_source_intake` record has no checks (the runtime refused it; the schema allowed it).
  - `tests/test_schema_consistency.py`: a validator for the schema subset in use; 52 records
    (2 valid, 50 mutations) checked by schema and runtime. Every schema rejection is a runtime
    rejection; the six runtime-only rules (calendar date, zero denominator, public host, URL
    characters, duplicate check id, blank text) are documented and each exercised. Enums,
    patterns, limits and versions are compared with the runtime's constants.
  - `tests/test_site_safety.py`: no HTML/code sinks in the dashboard scripts; a strict CSP with
    no inline or foreign script; hostile markup in a record reaches the site only as JSON data;
    duplicate record ids across files are refused.
  - `tests/test_amvo.py`: the symlink test skips, with its reason, where symlinks cannot be
    created (a host that cannot create one cannot be attacked with one); it runs on Linux CI.
  - `.github/workflows/ci.yml`: Ubuntu and Windows × Python 3.11 and 3.13; gates named B01–B08;
    B08 fails on any tracked change after the build.
- **Run (Windows, Python 3.14.5):** `python -m compileall -q amvo tests`;
  `python -m unittest discover -s tests -v` → **41 run, 40 pass, 1 skipped, 0 fail, 0 error**;
  `validate` → 2 records; `audit-public` → 2 passed screening; `verify` and `build-site` exit 0.
- **Evidence (SHA-256):** `build/verification.json` `30e5329fdb52226710971a7e3053f097b6313a8906a0a690073ce7fe3ac3daeb`;
  `site/data/index.json` `3d4ed92ba87fba2ebbcec1b56598480d6e1331d65885e0c9386b7f589a0a1cfc`;
  `schemas/case.schema.json` `2a55401ecaaf62d466551ef51b2a5cbd2adb2add63f2b78196e83f0b8c088cb7`.
  (Reports are deterministic: same inputs, same bytes.)
- **Real data:** none fetched; both records are the existing fixtures.
- **Limits:** no remote pin is verified (`source_pin_verified` stays `false`); the URL host rule is
  syntactic, not DNS resolution — fetching (P1-A) must resolve and re-check every address it
  connects to; `audit-public` is pattern screening, not a privacy guarantee.
- **Next executable gate:** P1-A — opt-in, allowlisted, size-capped pin replay for `git_commit`,
  `arxiv_version` and `sha256`, offline fixtures first.

## P1-A — source pin replay (v0.1.3)

- **Base:** P0 `ab9a355` (`feat/p0-reproducible-baseline`). Branch `feat/p1a-source-pin-replay`.
- **Scope:**
  - `amvo/provenance.py` (new): `replay-pins` asks the origin whether a declared pin exists and
    matches — GitHub's commit API for `git_commit` (40-hex only; a 64-hex pin is `unsupported`
    there), arXiv's export API for `arxiv_version`, and the file itself for `sha256` on an
    allowlisted host. Fetching is opt-in (`--network`), HTTPS only, three hosts only
    (`api.github.com`, `export.arxiv.org`, `raw.githubusercontent.com`), no credentials, no
    redirects, 4 MB cap, 20 s timeout. Every resolved address must be global; the TLS
    connection goes to the address that was checked (SNI and certificate check use the host
    name), so a second DNS answer cannot steer it elsewhere.
  - Captures: one canonical JSON file per replay under `evidence/provenance/<record-id>/`,
    created exclusively (never overwritten); the latest one decides the record's state and the
    rest stay as history. A capture keeps identifiers, dates and hashes — never the source text.
    A capture is checked for self-consistency (schema, record id, pin, network mode, timestamp,
    `observed_sha256`, and that a `verified` capture observed the pinned value); it is a
    recorded observation, not a signed attestation — anyone can re-run the replay.
  - Report: new `source_pin_status` (`no_pin`, `declared_only`, `fixture_only`, `verified`,
    `mismatch`, `not_found`, `unavailable`, `unsupported`, `capture_invalid`) and
    `source_pin_capture`. `source_pin_verified` is `true` only for a live capture that matched.
    The P0 contract said this field would not change silently; it is changed here, in the
    open, with the engine version raised to `0.1.3` and the contract text updated.
  - Dashboard: each pinned card states its pin state in words; only a live match reads as
    checked, and every other state says what it is not.
  - `cases/amvo-openai-math-snapshot-1581d4c.json` (new): an intake record pinning public commit
    `1581d4cbdd69a0faf34b2089614fe2a814316a6a` of `openai/math`; metadata only, no checks.
- **Acceptance (matrix C):** S01/S04/S06 — a pin without a capture is `declared_only`;
  S02 — a 64-hex commit is accepted as a declaration and reported `unsupported` for GitHub
  replay; S03/S05/S07/S08/S09 — still refused at intake (P0 tests); S11 — a capture of an
  earlier pin is history, not the current state; S12 — DNS failure, private address, redirect
  or oversized body is `unavailable`, never a pass. S10 (withdrawal) belongs to P1-B.
- **Run (Windows):** Python 3.14.5 and 3.13.13 — `python -m unittest discover -s tests` →
  **56 run, 55 pass, 1 skipped, 0 fail, 0 error** (15 new in `tests/test_provenance.py`, all
  offline: the live code path runs against a fake resolver and connection). `validate` → 3
  records; `audit-public` → 3 passed screening; `verify` twice → identical bytes; `build-site`
  exit 0.
- **Real data:** one live replay, `python -m amvo replay-pins --network --case
  amvo-openai-math-snapshot-1581d4c`, 2026-10-13T10:02:27Z → `verified`: GitHub reports commit
  `1581d4c…` in `openai/math`, committed 2026-10-12T21:55:24Z, tree `45074722…`, two parents;
  5,884 bytes read, one request.
- **Evidence (SHA-256):** capture
  `evidence/provenance/amvo-openai-math-snapshot-1581d4c/20261013T100227Z-git_commit-1581d4cbdd69.json`
  `2d7c4d3721acc51b06a74f8922ce8aec0db4488b4f327eb94a06336b2bdc91af`;
  `build/verification.json` `5d6de77b7a83ba427e60ce3ed7c947d1c69f3ef319ab8d074d9d0e70ec1cadce`;
  `site/data/index.json` `b33e8c693500b9c2c453da3ec15a10f45ffc13d1956f3e83c2d3d40d5b54ad0f`;
  `schemas/case.schema.json` `0dede5b75205ea4d228e23c1cda3be5767e13227fe5d50a4aa0f5d0aa808667b`.
- **Limits:** a verified pin says which public version is meant, not that anything in it is
  true; GitHub's answer is trusted as the origin's own statement (no independent clone, no
  signature check); arXiv and `sha256` replay are tested offline only — no live arXiv or file
  pin exists yet; CI never touches the network.
- **Next executable gate:** P1-B — append-only correction / withdrawal events
  (`supersedes`, `corrects`, `withdraws`, `rebuttal`) with synthetic multi-version fixtures.

## P1-B — correction and withdrawal events (v0.1.4)

- **Base:** P1-A `9f9819d` (`feat/p1a-source-pin-replay`). Branch `feat/p1b-correction-events`.
- **Scope:**
  - `amvo/lineage.py` (new): an append-only ledger `events/ev-<seq>.json` with four event types
    — `withdraws`, `supersedes` (with `by`), `corrects`, `rebuttal`; all but `supersedes` need a
    public `source_url`. Each event stores `target_sha256` (and `by_sha256`) — the hash of the
    record as it stood — and `prev_sha256`, the hash of the event before it.
    - A record edited after an event named it, or removed, fails every command; the remedy is a
      new record plus a `supersedes` event.
    - An edited, removed or renumbered earlier event breaks the chain; `recorded_at` may not go
      backwards. Withdrawing twice, superseding twice, self-supersession and supersession cycles
      are refused.
    - Closing an objection is not modelled, so a recorded objection is never silently closed.
  - `record-event` CLI: builds the next event, checks it with the whole ledger, and creates the
    file exclusively; a refused event writes nothing.
  - Report: each case gains `lineage` (`state` current / superseded / withdrawn, with pointers
    and event lists); the report gains `event_ledger` (count and head hash). Outcomes are not
    rewritten by events. `audit-public` also screens event text.
  - `schemas/event.schema.json` (new) and `tests/test_event_schema.py`: 30 ledgers, every schema
    rejection is a runtime rejection; six runtime-only rules (calendar time, blank text, public
    host, event id matches seq, hash chain, record exists and is unchanged), each exercised.
  - Dashboard: a withdrawn or superseded record is labelled as such, its outcome shown only as
    "before withdrawal / before replacement"; it is not counted in the current-result totals and
    the outcome filters show current records only (two new filters list the others).
  - CI: gate **B07** fails a pull request that modifies, deletes or retypes any file under
    `events/` or `evidence/provenance/` (diff of the merge commit against its first parent;
    checkout depth 2). Checked on a throwaway clone: an edited capture is reported, an added
    event is not.
- **Acceptance:** matrix C S10 (withdrawn record kept, shown as withdrawn) and S11 (a new
  version is a new record; the old one keeps its hash, time and objections); Phase 2 exit
  "withdrawn is not read as currently established" — on a synthetic demo site (one superseded
  record with an objection, its replacement with a correction, one withdrawn record) the
  page counts 1 current pass out of 3, labels the other two, and the "bounded pass" filter
  lists only the current one. Console clean.
- **Run (Windows):** Python 3.14.5 and 3.13.13 — `python -m unittest discover -s tests` →
  **73 run, 72 pass, 1 skipped, 0 fail, 0 error** (17 new). `validate` → 3 records, 0 events;
  `audit-public` → passed; `verify` twice → identical bytes; `build-site` exit 0.
- **Evidence (SHA-256):** `build/verification.json`
  `abe05b26c8b9f7f2308dadfbc5e05414fb719c340a3c0b7e7da692ee54fe6096`; `site/data/index.json`
  `6dfb259377552729c5177e8ff5311ee279c101c5afca8ef74931fb7d40f32a82`;
  `schemas/case.schema.json` `e58fe44f95988960f6b19d8f1f9ac8d1d19c0e04754ef2fdb65f3b35fc4649ee`;
  `schemas/event.schema.json` `6f81db70a2b67cb187848839127b9e3e253f27a23c9137810b444719247ed0b9`.
- **Real data:** none. The ledger is empty; per the handoff, multi-version and conflict cases are
  synthetic only in this phase.
- **Limits:** removing or editing the newest event is not visible to the chain itself; only B07
  catches it, and only in a pull request (a direct push to `main` bypasses it). Events are not
  signed: `recorded_by` is a declared role, not an authenticated identity.
- **Next executable gate:** P1-C — Source / Claim / FormalTarget / Evidence / Review /
  Publication layering, with a v0.1 → v0.2 migration that keeps the old records' bytes and hashes.
