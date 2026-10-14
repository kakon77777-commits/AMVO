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
