# Portfolio standards pin and provenance

Swelter vendors the released portfolio standards tag **v3.0.1**. The canonical source is
<https://github.com/ChelseaKR/portfolio-standards>; the tag resolves to commit
`96822bb304506715faeb6f91b89c9f075e9af186`.

The vendored subset is under [`docs/standards/`](standards/), and the declared release is recorded
in [`docs/standards/.standards-version`](standards/.standards-version). On 2026-10-02 the set was
exported from the `v3.0.1` tag with upstream's `automation/vendor-standards.sh`, and every vendored
Markdown file was byte-compared to the same path in the signed `portfolio-standards-3.0.1.tar.gz`
release archive (whose `SHA256SUMS` entry and Sigstore bundle verified); all seventeen matched.
v3.0.1 is a patch release (re-verified stamps, text corrections, and tooling fixes) with the
same seventeen-document set as v3.0.0. The local checkout of a future or dirty standards branch
is not policy and is never used as the comparison target.

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

Last verified: 2026-10-02. Recheck cadence: on every standards-version change and quarterly.
