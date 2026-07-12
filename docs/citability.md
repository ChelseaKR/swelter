# Citability — how to cite swelter, what is staged, what remains

This page tells a researcher how to cite swelter today, and tells the maintainer exactly what
remains to turn the staged metadata into a DOI and a JOSS submission. Everything on this page is
docs-and-metadata only; nothing here changes the pipeline.

## How to cite swelter today

Use the metadata in [`CITATION.cff`](../CITATION.cff) — GitHub renders it as a "Cite this
repository" button on the repo page, with APA and BibTeX output. Until a DOI exists, cite the
repository URL and the version:

> Kelly-Reif, C. (2026). *swelter* (Version 0.1.0) [Computer software].
> https://github.com/ChelseaKR/swelter

Observation *data* is CC0-1.0 (see [`DATA-LICENSE`](../DATA-LICENSE)); the code is Apache-2.0.
Citing a data export means citing the software plus the export's coverage banner (the
`swelter export` summary line carries the window and calibration provenance).

## What is staged in this repo

| Artifact | Status | Purpose |
| --- | --- | --- |
| [`CITATION.cff`](../CITATION.cff) | Present, current (v0.1.0) | GitHub cite button; general citation metadata |
| [`.zenodo.json`](../.zenodo.json) | Staged | Metadata Zenodo uses when the GitHub webhook archives a release. Mirrors `CITATION.cff`; when both exist, Zenodo prefers `.zenodo.json`. JSON cannot carry comments and Zenodo rejects unknown keys, so the maintainer notes live here and in the `CITATION.cff` comment block. |
| [`paper/paper.md`](../paper/paper.md) + [`paper/paper.bib`](../paper/paper.bib) | Draft | JOSS submission draft. Every reference was verified against the publisher/agency page on 2026-07-09. |

## Owner steps remaining (UI actions a PR cannot perform)

1. **Enable the Zenodo GitHub webhook.** Log in at [zenodo.org](https://zenodo.org) with the
   GitHub account, open *GitHub* under account settings, and flip the toggle for
   `ChelseaKR/swelter`. This is a one-time UI action by the repo owner.
2. **Cut a tagged release.** Publish a GitHub release (e.g. `v0.1.0` at the current changelog
   line, or the next version). Before tagging, confirm `version` and `date-released` in
   `CITATION.cff` and `version` in `.zenodo.json` match the tag — they are set manually, not
   derived.
3. **Zenodo mints the DOI.** The webhook archives the release and mints a version DOI plus a
   concept DOI (stable across versions). Then, in a follow-up commit: uncomment and fill the
   `doi:` line in `CITATION.cff` with the **concept DOI**, and optionally add the DOI badge to
   the README (README edits are the owner's; this repo's contract forbids agents touching it).
4. **Submit to JOSS when ready.** [JOSS](https://joss.theoj.org) requires the archive DOI from
   step 3, a tagged release, and an author who responds to reviewer issues for the duration of
   the review (typically weeks to a few months). Submission timing — and whether the maintenance
   commitment fits right now — is the owner's call. The draft in `paper/` is written against
   what is on `main` today; re-read it before submitting if the feature surface has moved.

## Release checklist addition

Each release: bump `version` (and `date-released`) in `CITATION.cff`, bump `version` in
`.zenodo.json`, tag, publish. Zenodo re-archives every subsequent release automatically once the
webhook is on; the concept DOI keeps pointing at the latest.

Last verified: 2026-07-09. Recheck at each release, and if Zenodo's GitHub integration or JOSS
submission requirements change.
