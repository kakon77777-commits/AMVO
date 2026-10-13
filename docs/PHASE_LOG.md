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
