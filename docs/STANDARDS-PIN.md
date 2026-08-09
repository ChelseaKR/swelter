# Portfolio standards pin and provenance

Swelter vendors the released portfolio standards tag **v2.0.0**. The canonical source is
<https://github.com/ChelseaKR/portfolio-standards>; the tag resolves to commit
`e9cddffff4e9f685642f4ac2c90ddbca12bcebf3`.

The vendored subset is under [`docs/standards/`](standards/), and the declared release is recorded
in [`docs/standards/.standards-version`](standards/.standards-version). On 2026-08-09 every vendored
Markdown file was byte-compared to the same path at `v2.0.0`; all sixteen matched. The local checkout
of a future or dirty standards branch is not policy and is never used as the comparison target.

The verification contract is:

1. parse `standards_version` and require a released `vMAJOR.MINOR.PATCH` tag;
2. resolve that exact tag, never a floating branch;
3. compare each vendored Markdown file byte-for-byte to the tagged blob;
4. reject missing, extra, or locally edited standard documents; and
5. apply the documented currency rule against the latest released tag.

`make standards-pin` is the dependency-free offline layer: it proves the committed manifest, exact
file set, and bytes without pretending that self-committed metadata authenticates upstream.
`make standards-pin-upstream` is the hosted-CI layer: it reads stable releases from the canonical
GitHub repository, fetches the exact tag from its canonical Git remote, checks the peeled commit and
every tagged blob, and enforces the one-minor currency window. A release API or Git failure fails the
upstream gate; it never silently falls back to the local assertion.

Last verified: 2026-08-09. Recheck cadence: on every standards-version change and quarterly.
