# Layered registry (record format v0.2)

A published result is not one record. It is filed by layer, one immutable JSON object per file:

| directory | layer | what it holds |
|---|---|---|
| `sources/` | Source | a public origin — a repository, a preprint — with authors, canonical URL and rights |
| `revisions/` | SourceRevision | one fixed version of a source: a commit, an arXiv `vN`, a file hash |
| `claims/` | Claim | one statement as the source makes it (theorem, lemma, conjecture…), in one revision |
| `formal_targets/` | FormalTarget | a formal statement meant to correspond to a claim, with its code pin and toolchain |
| `evidence/` | Evidence | a check AMVO can compute about a claim; the result is computed, never stored |
| `reviews/` | Review | a review of a claim, with the reviewer's class, independence and conflicts |
| `publications/` | Publication | a report about claims, citing only evidence objects of those claims |
| `migrations/` | — | one manifest per v0.1 case: its canonical hash and the objects made from it |

References are `{"id", "sha256"}`, the referent's canonical hash. Editing an object that anything
refers to makes validation fail — register a new object instead. Nothing here records a verdict:
the report computes statuses from evidence, reviews and events, and none of them says *verified*.

**Where does a result go?** Ask first:

```bash
python -m amvo locate --query <source URL, arXiv id with vN, commit, or registry id>
```

It names the source, revision and claims already registered, or the source id and canonical URL
a new one would get. One source per canonical URL, one revision per pin, one claim per statement
in a revision, one evidence object per check: a second copy is refused.

Add objects from drafts whose references are bare ids (source and pinned revision ids are
derived when left out):

```bash
python -m amvo register --draft draft.json
python -m amvo registry-report --output build/registry.json
```

The v0.1 files in `cases/` are kept byte for byte; `python -m amvo migrate` adds the objects and
manifests for any case not yet migrated, and re-running it changes nothing. Format:
`schemas/registry.schema.json`. CI gate B07 refuses a pull request that changes or deletes a file
here (this README excepted).
