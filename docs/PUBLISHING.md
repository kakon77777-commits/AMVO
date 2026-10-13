# AMVO reporting and publication boundary

The observatory can supply evidence for a separate EveMissLab publication hub, AI mathematics magazine, website story or research synthesis. **Journalism is not verification**, and a generated article is not a new mathematical result.

Every article must separate the original author's claim, the evidence AMVO actually reproduced, independent external objections, unsolved dependencies, reference versions, license status and editorial commentary. Report withdrawals and corrections at least as visibly as favorable results.

Crediting an independent verifier does not transfer authorship of the original discovery. Disclose human versus AI contributions and avoid fabricated interviews, sources, academic reviews or proof certificates.

For book or magazine publication, separately check the current license and distributor rules at publication time. Do not automatically mirror third-party paper text in a paid or free publication.

## Deploying the observatory site

The site at `amvo.evemisslab.com` is generated from this repository; nothing in `site/` is
committed. Deploy only after the gates pass on the commit being deployed, and only with the
maintainer's go-ahead — a deploy publishes.

```bash
python -m unittest discover -s tests
python -m amvo validate
python -m amvo audit-public
python -m amvo build-site --output site
npx wrangler deploy
```

`wrangler.jsonc` makes an assets-only Worker (no Worker code runs) bound to the custom domain.
`web/_headers` is copied into the build and applied by the platform: a strict CSP with
`frame-ancestors 'none'`, `Referrer-Policy: no-referrer`, `nosniff`, and `Cache-Control: …
no-transform`, which stops edge features from rewriting pages (for example injecting an analytics
beacon — the site promises no trackers). After a deploy, check the live response headers and that
`/data/index.json` is byte-identical to the local build.
