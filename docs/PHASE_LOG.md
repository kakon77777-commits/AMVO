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

## P1-C — layered registry and v0.1 → v0.2 migration (v0.1.5)

- **Base:** P1-B `1ac50d3` (`feat/p1b-correction-events`). Branch `feat/p1c-layered-registry`.
- **Scope:**
  - `amvo/registry.py` (new): record format v0.2, one immutable object per file in
    `registry/<layer>/<id>.json` — Source, SourceRevision, Claim, FormalTarget, Evidence, Review,
    Publication — with ids that name their layer (`amvo-src-…`, `amvo-clm-…`, …) and references
    `{id, sha256}` to the referent's canonical bytes.
    - Hard rules from the master plan, enforced: evidence cannot rewrite its claim (editing a
      referenced object fails validation), a review has no source fields, a publication cites
      only evidence objects of the claims it reports (an id of another layer is refused), an
      evidence object and its formal target belong to the same claim, a claim needs a pinned
      revision unless its source is synthetic (T06). No object stores a verdict.
    - Duplicates refused: one source per canonical URL (GitHub repository paths lower-cased,
      `.git` and sub-paths dropped; arXiv sources versionless, the `vN` goes in a revision),
      one revision per pin, one claim per whitespace-normalised statement in a revision, one
      evidence object per check of a claim.
  - `locate --query <url | pin | id>` names the source, revision and claims a result already
    has, or the source id and canonical URL a new one would get; `register --draft FILE` adds
    one object from a draft with bare-id references, checked against everything registered,
    written exclusively (an identical file is "unchanged", a different one is refused).
  - `migrate`: each v0.1 case becomes v0.2 objects plus `registry/migrations/<case-id>.json`
    binding the case's canonical SHA-256; the case files are not touched; re-running adds
    nothing. Intake placeholder claim text is not turned into a Claim; a `review.status` is not
    turned into a Review. The repository's three cases are migrated (2 sources, 2 revisions,
    1 claim, 1 evidence object); the two openai/math records share one source, and the second
    manifest says which of its source fields (rights) were not carried.
  - `registry-report`: per-layer counts (sources, revisions, pinned / pin-verified revisions,
    claims by type, current claims with a bounded pass / not checked / not passed, formal
    kernel runs = 0, theorems proved = 0) and per-claim statuses from the contract vocabulary
    (`NOT_CHECKED`, `REPRODUCIBILITY_ONLY` for hash-only evidence, `BOUNDED_PASS`,
    `CHECKS_NOT_PASSED`, `SEMANTIC_ALIGNMENT_PENDING`, `OBJECTION_OPEN`, `SUPERSEDED`, `WITHDRAWN`,
    `INDEPENDENT_REPLICATION_PENDING`, `PUBLISHED_REPORT`). A claim inherits its v0.1 record's
    events through the manifest and withdrawal from its revision or source; a revision's pin
    state reads captures filed under its own id or under the v0.1 records it came from — the
    openai/math snapshot revision is `verified` through the P1-A capture. `build-site` adds the
    report to `data/index.json` as `registry`.
  - `schemas/registry.schema.json` (new; its check, pin, fraction and rights definitions are
    copied from the case schema and a test keeps them equal) with a one-way consistency test of
    33 registries; six runtime-only rules (canonical spelling, public host, calendar date, blank
    text, duplicate, unresolved reference), each exercised.
  - `amvo/core.py`: the check validator is shared by v0.1 records and v0.2 evidence.
  - CI B07 also covers `registry/` (README files excepted).
- **Acceptance:** P06 — a synthetic paper with a theorem, a lemma and a conjecture counts as
  1 source and 3 claims, 1 of them with a bounded pass, 0 theorems proved; T02 — hash-only
  evidence is `REPRODUCIBILITY_ONLY`, never `BOUNDED_PASS`; T04/T05 — a formal target gives
  `SEMANTIC_ALIGNMENT_PENDING` and `formal_kernel: not_run`; T06 — unpinned real revisions are
  refused; T07/S10 — a withdrawal of a revision withdraws its claims without erasing their
  computed results; S11 — a new arXiv version is a new revision beside the old one.
- **Run (Windows):** Python 3.14.5 and 3.13.13 — `python -m unittest discover -s tests` →
  **95 run, 94 pass, 1 skipped, 0 fail, 0 error** (22 new in `tests/test_registry.py`).
  `validate`, `audit-public`, `verify` (twice, identical), `registry-report` (twice,
  identical), `build-site`, and a second `migrate` (0 new objects) all exit 0.
- **Evidence (SHA-256):** `build/verification.json`
  `6676590840cf1b8043e9898fe88f8287f517bd66e94c51a438c0ab6cddaecc7e`; `build/registry.json`
  `2272ac15369f0fe587b61064f9da39859d3f128416f4b93ac0c63fdfd8b95233`; `site/data/index.json`
  `ae21ee661f5ae7b1309283c67c477c8063165ecea39c68dfea1f8aac8e41adac`;
  `schemas/case.schema.json` `06e23ad3e249ba5e94bef18306ba7f1a0d32bfd049f734600d227f2dd86454af`;
  `schemas/event.schema.json` `475374d693ebd1ee22223484537dfaaac33ac57cac1cb71186ce20b625d063a6`;
  `schemas/registry.schema.json` `5473f73ab4bfb3131f41ef8d4172a611ab1c2ae0b8f196e851d7d9908481bc25`.
- **Real data:** the migrated repository cases only; no new external source was added.
- **Limits:** claim decomposition of a real paper is not automated — a person registers each
  claim from a draft; duplicate detection is exact after normalisation, so a reworded statement
  of the same theorem is not caught; `replay-pins` still replays v0.1 records only (v0.2
  revisions read their captures); the dashboard does not yet render the layered report (P1-D).
- **Next executable gate:** P1-D — a front-end report from the layered data: original authors,
  source version, last check and its method, results, unknowns and the correction chain, with
  `UNKNOWN` / `NOT_CHECKED` for everything not actually checked and never `VERIFIED`.

## P1-D — front-end report and site deployment configuration (engine unchanged, v0.1.5)

- **Base:** P1-C `ce35403` (`feat/p1c-layered-registry`). Branch `feat/p1d-frontend-report`. The
  engine and its reports are unchanged, so the version stays `0.1.5`; `data/index.json` is
  byte-identical to P1-C's.
- **Scope:**
  - `web/index.html`, `web/app.js`, `web/styles.css`: the page renders the layered report
    (`data/index.json` → `registry`) claim by claim. Each claim card shows its statuses, type and
    location, the exact statement and scope, and then:
    - original authors and publisher; the source, linked;
    - source version with its pin state (only a live, matching capture reads as checked, with
      its date);
    - the checks actually computed — kind, PASS / FAIL / ERROR, and what the check bounds — or
      `NOT_CHECKED`;
    - who recomputed it (the engine id, at site build; not a human review);
    - unknowns, always listed: formal kernel `NOT_RUN`, semantic alignment `UNKNOWN` /
      `NOT_CHECKED`, independent review `NOT_CHECKED` (or the reviews on file), novelty
      `UNKNOWN`, general truth `UNKNOWN`;
    - the correction chain: every event naming the claim, its revision, its source or the v0.1
      record it came from.
    - Stats are per layer (sources, claims, current claims with a bounded pass / not checked,
      kernel runs, theorems certified); a source register lists each source's revisions and how
      many claims it has ("a registered source is not a checked claim"); a legend explains every
      status code. An unknown status code renders as "unknown", never as a pass.
  - `web/_headers` (CSP with `frame-ancestors 'none'`, `no-referrer`, `nosniff`,
    `Permissions-Policy`, COOP, HSTS, `Cache-Control … no-transform`), `web/404.html`, and
    `wrangler.jsonc` (assets-only Worker `amvo`, directory `./site`, custom domain
    `amvo.evemisslab.com`, `not_found_handling: 404-page`). `build-site` copies all five web
    files. `docs/PUBLISHING.md` gives the deploy steps; deploying stays a separate decision.
  - Tests (`tests/test_site_safety.py`, 4 new): every report status has a label and every pin
    state has a label (keys compared with the engine's constants); no label the script can
    render says verified / proved; the built site carries the layered report with
    `theorems_proved` 0; the headers and Worker config are as above and no Worker code runs.
- **Checked in a browser:** with the repository data (1 claim, 2 sources) and with a synthetic
  demo (a theorem with a failing check and a formal target, a lemma with a bounded pass, a
  conjecture with a recorded objection): statuses, stats (1 source, 3 claims, 1 pass, 1 not
  checked) and the chain render as described; console clean; at 375 px wide nothing overflows
  (facts and legend single-column, stats two-column). Under `wrangler dev` (4.150.0, the same
  assets runtime as production): `/` 200 with the CSP, `no-referrer`, `nosniff` and the
  `no-transform` cache header; an unknown path 404 with the 404 page; `/_headers` not served;
  `/data/index.json` served as `application/json`.
- **Run (Windows):** Python 3.14.5 and 3.13.13 — **99 run, 98 pass, 1 skipped, 0 fail, 0 error**.
  All CLI gates exit 0; two `build-site` runs give identical trees.
- **Evidence (SHA-256):** `site/index.html` `9dfca7571b1da89b4b1be825cecb5440ded598b309a4692ca7c4f48b20d5a6d2`;
  `site/app.js` `125adeb7b0e74e07869729a9ea8ec1a43f716b7d950700b4e8f690c3b128fa1a`;
  `site/styles.css` `ab5f214a4256aeb5f61e4dc18aac3864c3427e0f295665cfdde43ef706a63863`;
  `site/404.html` `eaaa62b22c20972e6fda8356d733c7f53515c5ae756494f2529e7d1f4cc1bd2b`;
  `site/_headers` `37a2348518c664971bf3084927fba89ac599caf028e36a7cfea7a4807d0b7283`;
  `site/data/index.json` `ae21ee661f5ae7b1309283c67c477c8063165ecea39c68dfea1f8aac8e41adac`;
  `wrangler.jsonc` `482c9e9e9402119370cf6cf31c7acaea7602689a3fc9a87180f1578fc5f18b8a`.
- **Not done:** the site is **not deployed** — that waits for the maintainer's go-ahead. The page
  is in Traditional Chinese only. The v0.1 per-record view was replaced by the claim view (the
  v0.1 records remain in `data/index.json`).
- **Next executable gate:** deploy to `amvo.evemisslab.com` when approved and check the live
  headers and data hash; then Phase 1's remaining exit item — metadata-only intake of about ten
  public, clearly licensed, versioned sources of different kinds, claim by claim through
  `locate` / `register`.

## Site deployment (after P1-D)

- **2026-10-13:** `amvo.evemisslab.com` deployed by the maintainer from main `f208395`
  (`python -m amvo build-site --output site`, then `npx wrangler deploy`, wrangler 4.150.0;
  Worker `amvo`, version `5964e6ab-f588-4111-a53d-68b7560ba0f1`).
- **Checked live:** the CSP (with `frame-ancestors 'none'`), `no-referrer`, `nosniff`, HSTS,
  COOP, Permissions-Policy and `Cache-Control … no-transform` are served; `/`, `app.js`,
  `styles.css` and `data/index.json` are byte-identical to the build (`data/index.json`
  `ae21ee661f5ae7b1309283c67c477c8063165ecea39c68dfea1f8aac8e41adac`); the only script on the
  page is `app.js` (nothing injected at the edge); an unknown path returns 404 with the site's
  page; `/_headers` is not served; `http://` redirects to `https://`.

## P1 pilot — ten openai/math result families, metadata only

- **Base:** main `f208395`. Branch `feat/p1-openai-math-pilot`.
- **Scope:** `tools/intake/openai_math.py` reads `CONTENTS.md` of `openai/math` at the
  already-verified commit `1581d4c` (fetched through AMVO's allowlisted fetcher, or from a
  local copy that must hash to `cc7c0b8a1cdedd845a777e77cf682657308503daf8346c1349e06e9259d063c2`),
  parses its 372 result families and 719 manuscript entries, and registers a fixed sample —
  results 001–003 and every 53rd from 054 to 372 (054, 107, 160, 213, 266, 319, 372), chosen by
  number rather than content — as ten Claims on the pinned revision, through the registry's own
  checks. Each claim quotes the repository's one-paragraph summary (Apache-2.0), lists its
  constituent manuscripts by title and path (no manuscript text is copied), notes a Lean link
  where CONTENTS.md gives one (6 of the 10), and reads `NOT_CHECKED` /
  `INDEPENDENT_REPLICATION_PENDING`. Re-running writes nothing. No formal target is registered
  yet: a Lean link is not a formal target until its statement, code pin, toolchain and axioms
  are recorded.
- **Counts after the pilot:** 2 sources, 2 revisions, 11 claims (10 theorems as stated by the
  source + 1 synthetic computation), 1 current claim with a bounded pass, 10 not checked,
  0 kernel runs, 0 theorems proved.
- **Run (Windows):** Python 3.14.5 and 3.13.13 — **103 run, 102 pass, 1 skipped** (4 new in
  `tests/test_intake_openai_math.py`, offline: parser, quoting without manuscript text, a copy
  that is not the pinned file refused, the registered pilot is exactly the fixed sample and
  unchecked). The page renders the eleven claims; no horizontal overflow at 1280 or 375 px.
- **Evidence (SHA-256):** `build/registry.json`
  `b5b68d1464f27bff45af32554bb280fc756507141e726ac69a4a6469ebdaccc8`; `site/data/index.json`
  `968cb195aeda939572662721c0ef1be9386619847df8dc7192534ee3ffc5a85a`.
- **Limits:** one source, not ten of different kinds — the pilot covers ten results of one
  public, licensed, versioned corpus; result summaries are the source's own wording, and the
  manuscripts may state more or less than the summary; the summary text keeps its inline
  HTML/LaTeX exactly as published, so the page shows it raw.
- **Next:** a separate, private intake workspace (to be designed) for the remaining 362
  families, exported to this registry through `register`.

## Erratum to the P1 pilot — result 107 listed 2 of its 3 manuscripts

- **Found** while measuring the whole corpus before the full intake: CONTENTS.md has 719
  manuscript lines, the pilot's parser read 717. One line carries an annotation after its link
  ("— secondary writeup", result 107 — in the pilot) and one path contains parentheses
  ("CAT(0)", result 337 — not in the pilot); the parser's pattern skipped both without saying so.
  The pilot entry above therefore says 17 manuscripts; the true number for the ten families is 18.
- **Recorded, not rewritten:** the registered claim `amvo-clm-openai-math-r107` stays as it was;
  `events/ev-000001.json` (`corrects`, source: CONTENTS.md at the pinned commit) names the
  omitted manuscript. It is the ledger's first real event and shows in the claim's correction
  chain on the site.
- **Fixed:** the parser now accepts an annotation and parentheses in a path, refuses any result
  or manuscript line it cannot parse, and checks the totals CONTENTS.md states in its header
  (719 manuscripts, 372 families — numbered 1 to 377 with five numbers unused). A re-run stops
  if a registered claim differs from today's parse unless a `corrects` event for it is on
  record. `record-event` can now name v0.2 registry objects (it only saw v0.1 records — a P1-C
  omission found by this first real use).
- **Run:** 104 run, 103 pass, 1 skipped. Re-running the intake: 0 new, 9 unchanged, 1 corrected,
  18 manuscripts listed.

## Intake batch 1 of 4 — openai/math results 004–098

- **Base:** `e786f79` (`fix/openai-math-intake-parser`). Branch `feat/intake-batch-1`.
- **How:** the remaining 362 result families are planned in four batches (91, 91, 91, 89, by
  number). They are prepared in a separate private intake workspace that keeps every family and
  manuscript at the pinned commit with provenance per value; it was first checked to reproduce
  the nine uncorrected pilot claims byte for byte (and to differ, as it should, on r107, under its
  erratum). Each batch is built with this repository's own `claim_for` and checked by its own
  registry rules before anything is written; this repository does not read the workspace.
- **This batch:** 91 claims, results 004–098 (skipping the pilot's 054), 45 with a Lean link,
  184 manuscripts listed. All read `NOT_CHECKED` / `INDEPENDENT_REPLICATION_PENDING`.
- **Counts:** 2 sources, 102 claims, 1 current claim with a bounded pass (the synthetic one),
  101 not checked, 0 kernel runs, 0 theorems proved.
- **Run (Windows):** Python 3.14.5 and 3.13.13 — 104 run, 103 pass, 1 skipped. `validate`,
  `audit-public` pass; the page renders 102 claims, console clean.
- **Evidence (SHA-256):** `build/registry.json`
  `149de3a2e09a945201c61d67d7efe561c2fdd68eaafd3349e3c98ef68eefd88a`; `site/data/index.json`
  `8e31342d04e6bb728880b96167d0ed6246a7378e26f3de7531e425ebb0b8f4b4`.

## Intake batch 2 of 4 — openai/math results 099–193

- **Base:** `feat/intake-batch-1`. Branch `feat/intake-batch-2`.
- **This batch:** 91 claims, results 099–193 (the pilot's families in this range aside), 76 with a Lean link. Built and checked as batch 1 was; before exporting, the intake workspace reproduced every claim registered so far byte for byte (r107 aside, under its erratum). All read `NOT_CHECKED` / `INDEPENDENT_REPLICATION_PENDING`.
- **Counts:** 2 sources, 193 claims, 1 with a bounded pass (the synthetic one), 192 not checked, 0 kernel runs, 0 theorems proved.
- **Run (Windows, Python 3.14.5):** Ran 104 tests in 5.363s, OK (skipped=1); `validate` and `audit-public` pass.
- **Evidence (SHA-256):** `build/registry.json` `01ac34ea57df9512bd880b4cae74961ec3409017d9debcaa566854eb799a78ff`; `site/data/index.json` `fcf8a26df110a07caf7a6ee280b2bc8d5671a5444e35feb67bd37511e826b096`.

## Intake batch 3 of 4 — openai/math results 194–286

- **Base:** `feat/intake-batch-2`. Branch `feat/intake-batch-3`.
- **This batch:** 91 claims, results 194–286 (the pilot's families in this range aside), 62 with a Lean link. Built and checked as batch 1 was; before exporting, the intake workspace reproduced every claim registered so far byte for byte (r107 aside, under its erratum). All read `NOT_CHECKED` / `INDEPENDENT_REPLICATION_PENDING`.
- **Counts:** 2 sources, 284 claims, 1 with a bounded pass (the synthetic one), 283 not checked, 0 kernel runs, 0 theorems proved.
- **Run (Windows, Python 3.14.5):** Ran 104 tests in 8.064s, OK (skipped=1); `validate` and `audit-public` pass.
- **Evidence (SHA-256):** `build/registry.json` `2332c9471151a1edea32deee64773b799c6ced03330dba743e07a8c54a645b8f`; `site/data/index.json` `cc10e9cd1b047487404c56009981b19ea757bb4f1c9fcf45b9090e2665dc75b7`.

## Intake batch 4 of 4 — openai/math results 287–377

- **Base:** `feat/intake-batch-3`. Branch `feat/intake-batch-4`.
- **This batch:** 89 claims, results 287–377 (the pilot's families in this range aside), 53 with a Lean link. Built and checked as batch 1 was; before exporting, the intake workspace reproduced every claim registered so far byte for byte (r107 aside, under its erratum). All read `NOT_CHECKED` / `INDEPENDENT_REPLICATION_PENDING`.
- **Counts:** 2 sources, 373 claims, 1 with a bounded pass (the synthetic one), 372 not checked, 0 kernel runs, 0 theorems proved.
- **Run (Windows, Python 3.14.5):** Ran 104 tests in 8.253s, OK (skipped=1); `validate` and `audit-public` pass.
- **Evidence (SHA-256):** `build/registry.json` `054bdf7730e866118ad2ab8cbdd5424f3bd876ee4c6c5937c1cd0c33c4fad635`; `site/data/index.json` `d02c7fef788f8fc348abcd1b05c34b68a7ea76fe850ee22f29e1b48caecb36e7`.
- **Corpus complete:** all 372 result families of openai/math at `1581d4c` are registered — 719 manuscripts listed, 242 Lean links — each as a claim nobody here has checked. The counts match the totals CONTENTS.md states.

## Cloud pilot — statements inside the ten pilot families, and their Lean formal targets

- **Base:** `5b96144` (`docs/cloud-pilot-brief`: the brief `docs/tasks/CLOUD_PILOT_2026-10-14.md` on main `92a4ce9`);
  CI green on both (runs 47 and 48). Branch `claude/friendly-sagan-bg5hof`, one cloud session. Baseline on Linux,
  Python 3.13.16: 104 run, OK; `build/registry.json` and `site/data/index.json` byte-identical to batch 4's.
- **Read, not run:** CONTENTS.md, the 18 manuscripts, the 6 Lean pages, the 11 comparator `.lean` files they list
  with their `.json` configurations, `lean/lean-toolchain`, `lean/lake-manifest.json` and the comparator README —
  55 files, 12.7 MB, from raw.githubusercontent.com at `1581d4c`. Every file's git blob id equals the one in that
  commit's tree (read from a blob-less bare clone; no checkout). No Lean, lake, comparator or script from the
  source was installed or run. Nothing fetched is committed except the quoted statements and hashes.
- **A. Statements.** Text from `pdftotext -raw -enc UTF-8` (poppler 24.02.0; raw mode keeps TeX's content order,
  so displayed formulas stay inside their statements); two extractions of each PDF are byte-identical, and
  `--pdfs` mode re-extracts and must reproduce the recorded text hash. Candidates: every line that begins with a
  numbered theorem, proposition, corollary or conjecture label set in bold in the PDF (284 such lines; 20 were
  cross-references that merely start a line). No numbered conjecture occurs. 423 lemma headings were not taken:
  no manuscript calls a lemma a main result. A statement runs from its heading to the line before the first
  upright prose line, `Proof` or the next heading, read from the PDF's fonts with pdfminer.six 20260107 (theorem
  bodies are italic); every boundary was reviewed, two were cut by hand at recorded text. The check — heading and
  statement, whitespace normalised, found in the normalised text on the recorded PDF pages — found **264 of
  264**. Kept **248** (45 theorems, 154 propositions, 49 corollaries) as claims
  `amvo-clm-openai-math-rNNN-msK-<thm|prop|cor>-<label>`, each with its family claim as parent, quoting the
  extracted text exactly (control and private-use characters the PDF fonts carry are kept; the scope says so).
  No duplicate statement occurred.

  | family · ms | pages | found | kept | held | rejected | lemma headings | fetch s | pdftotext s | pdfminer s |
  |---|---|---|---|---|---|---|---|---|---|
  | r001 ms1 Milne's rationality conjecture | 36 | 10 | 10 | 0 | 0 | 11 | 0.64 | 0.20 | 3.2 |
  | r002 ms1 Exact BSD from low Selmer corank | 94 | 28 | 22 | 6 | 0 | 45 | 0.72 | 0.57 | 6.2 |
  | r002 ms2 Selmer converse at every prime | 82 | 19 | 16 | 3 | 0 | 31 | 0.31 | 0.48 | 4.9 |
  | r002 ms3 Two-primary BSD, corank ≤ 1 | 164 | 52 | 50 | 2 | 0 | 84 | 0.36 | 1.01 | 13.5 |
  | r003 ms1 Quasi-Riemann hypothesis 7/8 | 199 | 17 | 16 | 0 | 1 | 47 | 0.32 | 1.23 | 15.8 |
  | r003 ms2 Quasi-Riemann hypothesis 11/12 | 49 | 8 | 8 | 0 | 0 | 15 | 0.33 | 0.36 | 5.0 |
  | r003 ms3 Landau–Siegel zeros | 9 | 2 | 2 | 0 | 0 | 4 | 0.29 | 0.07 | 1.3 |
  | r054 ms1 Irrational cubic fourfolds | 62 | 19 | 18 | 1 | 0 | 27 | 0.27 | 0.40 | 4.5 |
  | r107 ms1 Upper bound 9/4 | 13 | 3 | 3 | 0 | 0 | 6 | 0.26 | 0.11 | 1.0 |
  | r107 ms2 Below 2.258 (secondary writeup) | 83 | 20 | 19 | 1 | 0 | 26 | 0.27 | 0.42 | 6.1 |
  | r107 ms3 Staggered extraction | 35 | 5 | 5 | 0 | 0 | 6 | 0.35 | 0.20 | 2.6 |
  | r160 ms1 van der Waerden numbers | 25 | 8 | 8 | 0 | 0 | 15 | 0.28 | 0.14 | 1.6 |
  | r213 ms1 Percolation on the cubic lattice | 20 | 3 | 3 | 0 | 0 | 9 | 0.32 | 0.13 | 1.5 |
  | r213 ms2 Quasi-transitive graphs | 42 | 13 | 12 | 1 | 0 | 10 | 0.30 | 0.24 | 2.9 |
  | r266 ms1 Mutually unbiased bases in dim. 6 | 76 | 14 | 14 | 0 | 0 | 42 | 0.30 | 0.45 | 5.1 |
  | r266 ms2 Fourier certificates, order 6 | 35 | 7 | 7 | 0 | 0 | 7 | 0.29 | 0.16 | 2.7 |
  | r319 ms1 Hahn–Wilson counterexamples | 79 | 29 | 28 | 1 | 0 | 30 | 0.34 | 0.54 | 4.2 |
  | r372 ms1 Elasticity inverse problem | 24 | 7 | 7 | 0 | 0 | 8 | 0.35 | 0.14 | 2.0 |
  | **total, 18 manuscripts** | 1,127 | 264 | 248 | 15 | 1 | 423 | 6.3 | 6.9 | 84 |

  `ms` numbers a family's manuscripts in CONTENTS.md order (r107 ms2 is the manuscript added by `ev-000001`).
- **Not kept (one line each).** Rejected: r003 ms1 Proposition 5.1 (Completed cubic reflection) — 6,143
  characters, over the registry's 4,000-character statement limit. Held — the manuscript presents the result as
  someone else's, so the family attribution the brief asks for would credit it to the citing manuscript (a
  conflict with AGENTS.md rule 6, so it is stopped here, not decided); the manuscript's own words:
  - r002 ms1 Theorem 2.1 — "This is [23, Theorem 1.1]."
  - r002 ms1 Theorem 2.2 — "This is [24, Theorem 1.1]."
  - r002 ms1 Theorem 2.3 — "This is the Gross–Zagier–Kolyvagin theorem, using modularity [12, 17, 4]."
  - r002 ms1 Proposition 2.4 — "These are the arithmetic-volume identities of Cassels and the restriction-of-scalars comparison of Milne [6, 19]."
  - r002 ms1 Theorem 2.5 — "We use the theorem at the scope stated in [22, Theorem 1.2]."
  - r002 ms1 Theorem 2.7 — "The first formula is the conductor-one split Gross–Zagier formula in the normalization used in [12, Chapters I and V]"
  - r002 ms2 Theorems 2.1 and 2.2 — "These are OpenAI [62, Theorems 1.1 and 1.2]."
  - r002 ms2 Theorem 8.4 — "Existence, polarization and the de Rham assertions are Barnet-Lamb et al. [6, Theorem 1.2];"
  - r002 ms3 Theorem 2.2 — "We use the conductor-one Gross–Zagier theorem at a coprime split level"
  - r002 ms3 Theorem 11.3 — "The determinant assertion is the Johnson-Leung–Kings theorem in the form of [11,"
  - r054 ms1 Theorem 2.5 — "This is the projective case of [2, Theorem 0.1.1];"
  - r107 ms2 Theorem 3.2 — heading "Theorem 3.2 (Asymptotic sum inequality, Schönhage [24])"
  - r213 ms2 Theorem 2.2 — "We now invoke precisely the following external result. Theorem 2.2 (Hutchcroft [19, Theorem 1.2])"
  - r319 ms1 Theorem 7.1 — "We use the construction in the November 14, 2018 version (v2) of Pstrągowski’s preprint."

  Their verbatim statements stay in the data file, checked, so registering them later needs only an attribution
  decision.
- **B. Formal targets.** 15 FormalTargets, one per theorem the comparator configurations name for the 6 Lean
  pages: r003 5 (ζ, Dirichlet and Hecke 7/8 bounds; two Siegel-zero statements), r107 4 (ω ≤ 9/4, α > 93/200,
  rectangular ω < 523/250; ω < 2.371054886006746 over every field), r160 1, r213 2, r266 2, r372 1. Each records
  the declaration exactly as written (checked: occurs once in its file and is followed by `:=`), code pin
  `1581d4c`, toolchain `leanprover/lean4:v4.34.1` with Mathlib `d13f23b7`, the permitted axioms the configuration
  *declares* (propext, Quot.sound, Classical.choice — not checked), and the page's own words for what it
  formalises, quoted. They attach to the family claims, not to the new statement claims: matching a Lean
  statement to a manuscript statement would be the judgement this layer does not make. The six family claims
  now read `SEMANTIC_ALIGNMENT_PENDING` with `formal_kernel: not_run`. Lean page 266 itself says its formal
  statement is weaker than the paper (at most five bases, not three); that sentence is quoted in the target.
- **Tools:** `tools/intake/openai_math_statements.py` (+ `openai_math_statements.json`, the 264 candidates with
  PDF and text hashes) and `tools/intake/openai_math_formal.py` (+ `openai_math_formal_targets.json`, the 15
  targets with the hashes of the 33 files they rest on). Both check before writing, write through the registry's
  checks, refuse to rewrite an object and write nothing on a re-run (checked: 0 new, 248 / 15 unchanged).
- **Tests:** `tests/test_intake_openai_math_statements.py`, 8 new, offline (synthetic texts and Lean files):
  verbatim and page check, paraphrase / wrong page / unnormalised text refused, a cut-short quote is still found
  (the check proves a quote real, not complete), hold / too long / duplicate / foreign text, a whole declaration
  required, the page must contain every quoted sentence, a changed file refused, and every registered statement
  and target equal to what the data files produce. `tests/test_intake_openai_math.py`: family claims are now
  selected by `rNNN` exactly, and a family with a formal target expects `SEMANTIC_ALIGNMENT_PENDING` as well.
  Run (Linux, Python 3.13.16): **112 run, OK**; `validate` (621 claims, 15 formal targets), `audit-public`,
  `verify`, `registry-report` and `build-site` exit 0; reports identical across two runs. The built page, in
  headless Chromium: 621 claim cards, 6 marked 語義對齊未評估, no horizontal overflow at 1280 or 375 px.
- **Counts:** 2 sources, 621 claims (417 theorems, 154 propositions, 49 corollaries, 1 computation),
  15 formal targets, 1 current claim with a bounded pass (the synthetic one), 620 not checked, 0 kernel runs,
  0 theorems proved.
- **Evidence (SHA-256):** `build/registry.json`
  `2710e0d1ade5bcda39d90fc657adb8a3ca4ac38418782a4461cc2bb4e15cdef4`; `site/data/index.json`
  `e8fcd5d5fa24b9047ef7e6c8849a42be56c5d768a437e8197c19b88a977a822d`; `build/verification.json` unchanged
  `fcd1e68ea4cbf5493ef0f234f0a718460c570259e0491e74c66d346cd1b260fb`;
  `tools/intake/openai_math_statements.json` `8d93a9b8f1434af0bcc9b6cf0da6b44eff012ce77fd64f17057e314a58472575`;
  `tools/intake/openai_math_formal_targets.json` `799c3f3ced031b3a21dd4e337966ee0755aec60c7f639968c5daa83b463355d8`.
- **Cost (measured; container clock, UTC):** session 15:07:57 → 15:40:01 at the commit, about 32 minutes
  of wall time in all. Machine time is small: fetching 55 files 17 s, `pdftotext` 6.9 s and the
  pdfminer font pass 84 s for all 18 PDFs (1,127 pages); a full `--pdfs` re-check 16 s. The rest is the agent:
  setup and baseline 2 min; fetch, extraction and reading the Lean pages 6 min; building the boundary aid and
  reviewing the 18 manuscripts 8.5 min (3 short ones during calibration, then 9 s – 70 s each, longest r003 ms1
  and r002 ms1); data files, tools, tests and registration 10 min; gates, browser check and this log the rest.
  Tokens: the session's visible context counter fell from 15,000,000 to about 14.5 million, ≈ 0.5 M tokens of
  context in all, of which ≈ 0.17 M went to reading candidates (≈ 0.65 K per candidate, ≈ 9 K per manuscript on
  average, roughly proportional to the candidates shown) and the rest to setup, tooling, tests and records.
  Billed tokens and credits are not visible to the session. *Assumption, for planning only:* the remaining 701
  manuscripts of the corpus (719 − 18; the brief says 699) at the pilot's density (≈ 14.7 candidates and ≈ 28 s of
  review per manuscript) would mean ≈ 10,000 candidates, ≈ 7 M context tokens of review and ≈ 5–6 hours of agent
  time, split across sessions, plus about 6 s of machine time per manuscript; the tooling would not need
  to be rebuilt. The pilot sample was chosen by number, so its density need not be the corpus's.
- **Limits:** the quotes are extracted text, not typeset mathematics — superscripts, fractions, large operators
  and delimiters come out flattened or as font codes, so a quote can be hard to read and the PDF stays
  authoritative; the check proves a quote is real, not that it is complete — where a statement ends is the
  font hint plus review, which can be wrong; a statement that crosses a page keeps the page number between;
  near-duplicates are not detected (e.g. r003 ms1 Theorem 3.1 and r003 ms2 Theorem 1.1 both state the 11/12
  half-plane, in different words, and are both kept); whether a candidate is someone else's result was judged
  from the text around it and may have missed cases; formal targets carry declarations only, and the
  definitions they use are fixed by the code pin, not quoted.
- **Not done:** no merge, no deployment, no Lean run. The 15 held statements wait for an attribution decision.
- **Next:** decide how cited results are attributed (a separate attribution field, or none registered); then the
  remaining manuscripts in batches with the same two tools, measuring the same costs.

## Statements, batch r004–r049 — and the pilot's cited results registered

- **Decision (maintainer, 2026-10-14):** a result that a manuscript presents as someone else's is that work's
  result. It is registered, credited to that work in the manuscript's own words; anything wrong is later
  corrected by an event, never by rewriting. `openai_math_statements.py` gained the decision `cited`: the claim's
  attribution reads "Credited to the work the manuscript cites, not to OpenAI or the manuscript's authors", then
  the citing sentence and the manuscript's bibliography entries for its keys, each checked to occur verbatim in
  the extracted text. The 15 pilot candidates held above are now registered this way (pilot data file edited:
  `hold` → `cited`; its statements are unchanged). Pilot: 263 of 264 kept, 15 of them credited to cited work.
- **Batch:** result families 004–049 without the pilot's (45 families, 100 manuscripts, 4,715 pages, 59.3 MB),
  same commit, same extraction, same check. Base: `d8006e3` on this branch.
- **Process, changed from the pilot to read less:** the boundary aid now (a) stops on an upright line only when
  it starts at the left margin, so displayed formulas with roman words (`log`, `dim`, "odd and squarefree") no
  longer end a statement early; (b) skips and trims capitalised running heads and feet; (c) looks for a heading's
  bold row on its own page first. Review is by exception: only candidates with a boundary flag (statement not
  ending in `.`, `)`, `]` or `}`; empty; overlapping another heading; a label used twice) or a citation phrase
  near them were read — 127 of 1,219, with every decision recorded in the data file.
- **Result:** 1,219 bold-heading lines; 3 were cross-references that begin a line (not candidates); **1,216
  candidates, all found verbatim** on their recorded pages; **1,206 kept** (329 theorems, 712 propositions, 175
  corollaries — 55 of them credited to cited work); 9 statement ends cut by hand at recorded text; 1,690 lemma
  headings not taken. **Rejected (10), each a duplicate statement, the first kept:** r018 ms2 Theorem 4.1 (= r018
  ms1 Theorem 8.1); r034 ms4 Theorem 3.1, Propositions 4.1, 6.3, 6.6, 6.8, 6.10 and Corollary 6.4 (= r034 ms3 C.1,
  D.3, F.3, F.6, F.8, F.9, F.4); r034 ms13 Proposition 3.3 (= r034 ms11 Proposition 7.1); r036 ms3 Proposition 3.4
  (= r034 ms4 Proposition 10.1).
- **Tools and tests:** the statements tool takes `--data` per batch file, refuses two candidates mapping to one id
  before writing anything (a run that hit this was discarded before commit), and lets a repeated label carry an
  `id_suffix`. Tests: 113 run, OK (1 new: a cited result is credited to the cited work, and a citing quote not in
  the text is refused; the data test now covers every data file and the duplicate rule).
- **Counts:** 2 sources, 1,842 claims (758 theorems, 860 propositions, 223 corollaries, 1 computation), 15 formal
  targets, 1 bounded pass (synthetic), 1,841 not checked, 0 kernel runs, 0 theorems proved.
- **Evidence (SHA-256):** `build/registry.json`
  `0fcc31c951a7b393526914cabf76fe6fac01f1e87cdd986fa2f9517fc8aa11c3`; `site/data/index.json`
  `6d495eaba9e701ce5ff254dabbca0d8f01ae97598a0caaf3910520f532071fe4`;
  `tools/intake/openai_math_statements_r004-r049.json` `b14290cb18da82abd8ca8434d495c919a2924430fb74f57c327feccb19deb203`;
  `tools/intake/openai_math_statements.json` (after the edit) `7b40520857dce99fb47a7ba64fcd47bed1888abdb7a93aa88dd3ec7de61e4298`.
- **Cost:** 16:26 → 16:41 UTC, about 15 minutes of wall time, including the tool changes above. Machine time:
  83 s to fetch, extract (twice) and font-scan the 100 PDFs with 8 workers. Context used: about 0.14 M tokens
  (≈ 1.4 K per manuscript, ≈ 0.11 K per candidate) — a third of the pilot's rate per manuscript because only
  flagged candidates are read.

## Statements, batch r050–r099

- **Batch:** result families 050–099 without the pilot's (47 families, 87 manuscripts, 3,905 pages, 50.9 MB); same commit, extraction, check and review by exception as batch r004–r049.
- **Result:** 959 bold-heading lines; 2 of them not candidates (below); **957 candidates, all found verbatim** on their recorded pages; **954 kept** (251 theorems, 532 propositions, 171 corollaries — 28 of them credited to cited work); 10 statement ends cut by hand at recorded text; 1,417 lemma headings not taken.
- **Not candidates:** r055m1 line 943 — a section line that begins with the label; the heading is at line 948; r068m6 line 769 — a line that begins with the label after the statement; the heading is at line 745.
- **Rejected (3):** r056 ms5 Corollary 2.5: duplicate of amvo-clm-openai-math-r056-ms4-cor-2-5 (the first is kept); r056 ms5 Corollary 4.7: duplicate of amvo-clm-openai-math-r056-ms4-cor-4-7 (the first is kept); r056 ms5 Proposition A.1: duplicate of amvo-clm-openai-math-r056-ms4-prop-a-1 (the first is kept).
- **Tests:** 113 run, OK; `validate`, `audit-public`, `verify`, `registry-report`, `build-site` exit 0.
- **Counts:** 2 sources, 2,796 claims (1 computation, 394 corollaries, 1,392 propositions, 1,009 theorems), 15 formal targets, 2,795 not checked, 0 kernel runs, 0 theorems proved.
- **Evidence (SHA-256):** `build/registry.json` `9449cf5a9ae7421a4bddc0f60e3cd98856a914551fc6d7db1848be113e98233d`; `site/data/index.json` `38731ad21ab0200df09c2a572a976b8becf57556ba901c9a287b0cf88ba1fd5f`; `tools/intake/openai_math_statements_r050-r099.json` `7376fd7fc9545f3a38fa35c0c527a7ea0fe63f3f02c60d1c636d55d81514262c`.
- **Cost:** 16:41 → 16:46 UTC wall time; 68 s of machine time to fetch, extract (twice) and font-scan the 87 PDFs; about 35 K tokens of context.

## Statements, batch r100–r149

- **Batch:** result families 100–149 without the pilot's (48 families, 85 manuscripts, 3,304 pages, 46.4 MB); same commit, extraction, check and review by exception as batch r004–r049.
- **Result:** 679 bold-heading lines; 1 of them not candidates (below); **678 candidates, all found verbatim** on their recorded pages; **677 kept** (253 theorems, 293 propositions, 131 corollaries — 19 of them credited to cited work); 6 statement ends cut by hand at recorded text; 1,186 lemma headings not taken.
- **Not candidates:** r108m1 line 1233 — a line that begins with the label after the statement; the heading is at line 1207.
- **Rejected (1):** r136 ms1 Theorem 6.1: statement has 4079 characters; the registry's limit is 4000.
- **Tests:** 113 run, OK; `validate`, `audit-public`, `verify`, `registry-report`, `build-site` exit 0.
- **Counts:** 2 sources, 3,473 claims (1 computation, 525 corollaries, 1,685 propositions, 1,262 theorems), 15 formal targets, 3,472 not checked, 0 kernel runs, 0 theorems proved.
- **Evidence (SHA-256):** `build/registry.json` `290d6ccc113391963754fd7250721c2cc317286a7f84acc26106341e1d431581`; `site/data/index.json` `10a39fb6fd2b5268b173e6898f3f46d7abe2dc456e9266152d6f2039837fbb6c`; `tools/intake/openai_math_statements_r100-r149.json` `9d2b4e3c1e263082b6d5e3f7138819b309af348ebce83f260809c96729e76694`.
- **Cost:** 16:44 → 16:49 UTC wall time; 64 s of machine time to fetch, extract (twice) and font-scan the 85 PDFs; about 30 K tokens of context.

## Statements, batch r150–r199

- **Batch:** result families 150–199 without the pilot's (48 families, 69 manuscripts, 2,723 pages, 37.9 MB); same commit, extraction, check and review by exception as batch r004–r049.
- **Result:** 560 bold-heading lines; 1 of them not candidates (below); **559 candidates, all found verbatim** on their recorded pages; **558 kept** (167 theorems, 285 propositions, 106 corollaries — 18 of them credited to cited work); 4 statement ends cut by hand at recorded text; 1,003 lemma headings not taken.
- **Not candidates:** r154m2 line 472 — a line that begins with the label after the statement; the heading is at line 396.
- **Rejected (0), held (1):** r187 ms1 Proposition 5: the extracted text interleaves a figure's labels and caption with this statement, so no verbatim quote of the statement alone exists.
- **Tests:** 113 run, OK; `validate`, `audit-public`, `verify`, `registry-report`, `build-site` exit 0.
- **Counts:** 2 sources, 4,031 claims (1 computation, 631 corollaries, 1,970 propositions, 1,429 theorems), 15 formal targets, 4,030 not checked, 0 kernel runs, 0 theorems proved.
- **Evidence (SHA-256):** `build/registry.json` `4b4494a6a8039a6af2152d1e68173bf5ac9447d911491df109f7e2f16ae72732`; `site/data/index.json` `1c5ae315e3c115b08314a6bd76a4ecb88437dc1c939c9d174bc50daae5dd4ab0`; `tools/intake/openai_math_statements_r150-r199.json` `4dad031b474818532cf2c10b8c654584151ba54da0a655fb7713e8dfee347f22`.
- **Cost:** 16:46 → 16:52 UTC wall time; 48 s of machine time to fetch, extract (twice) and font-scan the 69 PDFs; about 17 K tokens of context.

## Statements, batch r200–r249

- **Batch:** result families 200–249 without the pilot's (49 families, 134 manuscripts, 8,518 pages, 94.8 MB); same commit, extraction, check and review by exception as batch r004–r049.
- **Result:** 2,047 bold-heading lines; 1 of them not candidates (below); **2,046 candidates, all found verbatim** on their recorded pages; **2,028 kept** (500 theorems, 1241 propositions, 287 corollaries — 46 of them credited to cited work); 17 statement ends cut by hand at recorded text; 2,903 lemma headings not taken.
- **Not candidates:** r211m5 line 276 — a line that begins with the label after the statement; the heading is at line 223.
- **Rejected (17), held (1):** r216 ms6 Proposition 3.14: statement has 4435 characters; the registry's limit is 4000; r223 ms6 Theorem 1.2: duplicate of amvo-clm-openai-math-r223-ms1-thm-1-2 (the first is kept); r223 ms6 Proposition 3.2: duplicate of amvo-clm-openai-math-r223-ms1-prop-3-2 (the first is kept); r223 ms6 Proposition 5.3: duplicate of amvo-clm-openai-math-r223-ms1-prop-5-3 (the first is kept); r223 ms6 Proposition 8.1: duplicate of amvo-clm-openai-math-r223-ms1-prop-8-1 (the first is kept); r223 ms6 Proposition 9.2: duplicate of amvo-clm-openai-math-r223-ms1-prop-9-2 (the first is kept); r223 ms6 Theorem 9.3: duplicate of amvo-clm-openai-math-r223-ms1-thm-9-3 (the first is kept); r223 ms6 Proposition 10.1: duplicate of amvo-clm-openai-math-r223-ms1-prop-10-1 (the first is kept); r223 ms6 Corollary 10.2: duplicate of amvo-clm-openai-math-r223-ms1-cor-10-2 (the first is kept); r223 ms6 Proposition 12.2: duplicate of amvo-clm-openai-math-r223-ms1-prop-12-2 (the first is kept); r223 ms6 Corollary 12.6: duplicate of amvo-clm-openai-math-r223-ms1-cor-12-6 (the first is kept); r223 ms6 Theorem 12.9: duplicate of amvo-clm-openai-math-r223-ms1-thm-12-9 (the first is kept); r223 ms6 Proposition 13.4: duplicate of amvo-clm-openai-math-r223-ms1-prop-13-4 (the first is kept); r223 ms6 Proposition 14.3: duplicate of amvo-clm-openai-math-r223-ms1-prop-14-3 (the first is kept); r223 ms6 Proposition 14.4: duplicate of amvo-clm-openai-math-r223-ms1-prop-14-4 (the first is kept); r223 ms6 Proposition 15.7: duplicate of amvo-clm-openai-math-r223-ms1-prop-15-7 (the first is kept); r223 ms6 Theorem 15.8: duplicate of amvo-clm-openai-math-r223-ms1-thm-15-8 (the first is kept); r233 ms1 Corollary 9.3: the extracted text interleaves a figure's labels and caption with this statement, so no verbatim quote of the statement alone exists.
- **Tests:** 113 run, OK; `validate`, `audit-public`, `verify`, `registry-report`, `build-site` exit 0.
- **Counts:** 2 sources, 6,059 claims (1 computation, 918 corollaries, 3,211 propositions, 1,929 theorems), 15 formal targets, 6,058 not checked, 0 kernel runs, 0 theorems proved.
- **Evidence (SHA-256):** `build/registry.json` `30291c0bc276bc9ea6913fe39ea844d23f59661b91a14dcecc8b8814ad2070e9`; `site/data/index.json` `4f185b69b2618d9f1b8259a04d36dab86e7c6ac805114cd852e6eaa6e4d6484c`; `tools/intake/openai_math_statements_r200-r249.json` `8deb93f978b2a47efe766f0dfb3c5a98c53e204aa87e071231bb858e7ee08306`.
- **Cost:** 16:49 → 16:58 UTC wall time; 171 s of machine time to fetch, extract (twice) and font-scan the 134 PDFs; about 38 K tokens of context.
