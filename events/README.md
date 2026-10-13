# Correction and withdrawal events

This directory is an append-only ledger. A record in `cases/` is never edited to say it was
withdrawn, replaced, corrected or disputed; an event is added here instead, one file per event,
`ev-000001.json`, `ev-000002.json`, … Write them with the CLI, never by hand:

```bash
python -m amvo record-event --type withdraws --target <record-id> --source-url <public notice> --rationale "<why>" --recorded-by "<role>"
python -m amvo record-event --type supersedes --target <older-id> --by <newer-id> --rationale "<why>" --recorded-by "<role>"
```

Types: `withdraws` (the source withdrew it), `supersedes` (a newer record replaces it),
`corrects` (an erratum), `rebuttal` (a recorded objection or counterexample). Every type but
`supersedes` needs a public `--source-url` showing the event.

- Each event stores the SHA-256 of the record(s) it names. Editing such a record afterwards
  makes every command fail: publish a new record and a `supersedes` event instead.
- Each event stores the SHA-256 of the event before it, so editing or removing an earlier event
  breaks the chain. CI gate B07 refuses any pull request that changes or deletes a file here.
- Events never rewrite a record's computed outcome. The report shows the outcome and the
  record's lineage side by side, and the dashboard does not count a withdrawn or superseded
  record as a current result.
- `recorded_by` names a role (for example "AMVO maintainers"), not a private person.

The format is `schemas/event.schema.json`.
