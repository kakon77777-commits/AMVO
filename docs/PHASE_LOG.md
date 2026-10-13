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
