# Citability and archival

Software and data are cited separately because they have different versions, provenance, and rights.

Owner: Chelsea Kelly-Reif. Last verified: 2026-07-16. Recheck cadence: every release, snapshot-schema
change, or Zenodo/JOSS requirement change.

## Cite the software before a release DOI exists

Use [`CITATION.cff`](../CITATION.cff) and identify the exact commit. The repository currently prepares
version `0.2.0`, but there is no released date or DOI until an annotated tag and GitHub Release exist.

Suggested form:

> Kelly-Reif, C. (2026). *swelter* (0.2.0 release candidate, commit `<sha>`) [Computer software].
> https://github.com/ChelseaKR/swelter

Replace the release-candidate wording with the published version/DOI only after that release is
archived.

## Cite a dataset or export

`swelter snapshot` writes dataset-specific `DATA-CITATION.cff`, `CITATION.txt`, and `MANIFEST.json`
artifacts with version, coverage, record count, and hashes. Cite that snapshot plus its actual source
license/attribution artifacts. Do not cite the root `DATA-LICENSE` as though every fetched observation
were CC0:

- project-authored synthetic and authorized first-party observations may be CC0-1.0;
- OpenAQ data requires its per-location `source-license-ledger.json`;
- CAMS/Open-Meteo and Sensor.Community data retain upstream attribution and terms;
- contextual/reference layers retain their own source records.

[`data-cards/`](data-cards/README.md) and [`DATA-LICENSE`](../DATA-LICENSE) define the boundary.

## Release and DOI sequence

1. Verify the exact candidate and align `pyproject.toml`, the dated `CHANGELOG.md` section,
   `CITATION.cff`, and `.zenodo.json` to the same version. Add `date-released` only when the release
   date is real. Ensure `.zenodo.json` also uses source-specific data wording.
2. Enable the Zenodo GitHub integration for `ChelseaKR/swelter` from the repository owner's Zenodo
   account.
3. Create the annotated `v0.2.0` tag from the verified merge commit. Let the release workflow build,
   verify, sign, attest, and publish the artifacts.
4. Confirm Zenodo archived the GitHub Release and issued a version DOI and concept DOI.
5. Add the concept DOI to `CITATION.cff` in a follow-up change and cite the version DOI for that exact
   release where reproducibility matters.
6. Update any JOSS draft against the tagged source and submit only when the maintainer can support the
   review/maintenance commitment.

## Proving a snapshot re-derives

A snapshot's `MANIFEST.json` digests prove nobody edited the frozen files. They say nothing about
whether the published surface ever followed from the readings shipped beside it. `swelter
reproduce <snapshot-dir> --config network.yaml` closes that gap: it applies the frozen corrections
to the frozen raw observations, rebuilds the surface through the same path `swelter rebuild` uses,
and compares the result byte for byte, writing a receipt (`--receipt`) naming the inputs,
versions, digests, verdict, and first differing feature.

Three things a citing author should know (ADR 0049, `docs/api.md`).

- **It is an operator check, not a downloader check.** The network configuration is an input to
  the surface, and it stays out of the release because it holds precise host coordinates. The
  release records only a fingerprint, so reproducing it needs the operator's `network.yaml`.
- **A release that cannot be checked exits 2, not 0.** Snapshots written before `MANIFEST.json`
  carried `data_schema_version` and `config_fingerprint` report `indeterminate`. That is neither a
  pass nor a failure, and it does not share an exit status with success.
- **Cross-version reproduction is reported, not attempted.** Rebuilding an older release under a
  newer swelter would blame the data for a code change.

## Handing a release to an open-data portal

A citation makes a snapshot quotable. It does not make it *findable*: a CKAN instance
(`data.ca.gov`) or a Socrata portal harvests a Frictionless `datapackage.json` or a DCAT record,
and a release with neither is only reachable by someone who was already sent the link.

`swelter package <snapshot-dir> --out <dir>` writes both, plus a self-contained copy of the
release's data files and the tabular `export.csv` a portal previews. Three properties matter to a
citing author (ADR 0051, `docs/api.md`).

- **The digests are the release's own, verified first.** Every file is checked against
  `MANIFEST.json` before the package is written, and a mismatch refuses the whole operation by
  filename. The checksums a portal republishes are therefore the ones the release already
  published, not fresh hashes taken over whatever was on disk.
- **Rights are not flattened.** A source with per-location terms gets its own statement plus a
  path to the packaged `source-license-ledger.json`, never a single SPDX identifier swelter
  invented on its behalf.
- **Nothing is pushed.** This writes files. Submitting them to a portal is an operator action with
  its own credentials.

The generated descriptor was validated with `frictionless` 5.19.0 against the bundled demo release
(151,812 rows, `VALID`). That library is not a project dependency, so the validation is a recorded
measurement rather than a standing merge gate; adding it as one is tracked in
[#243](https://github.com/ChelseaKR/swelter/issues/243).

## Repository artifacts

| Artifact | Current role | Release requirement |
|---|---|---|
| `CITATION.cff` | Software citation metadata for GitHub and tools | Version matches tag; add real release date and DOI when available |
| `.zenodo.json` | Zenodo deposit metadata | Must match software metadata and source-specific rights wording |
| `CHANGELOG.md` | Human-readable release history | Dated section for the tag, with no fabricated earlier release |
| `paper/paper.md` / `paper/paper.bib` | Draft publication material | Re-verify claims, references, version, and evidence against tagged source |
| Snapshot citation/manifest | Dataset-specific citation and integrity evidence | Generated from the exact store/source set; terms/attribution retained |

No metadata file, badge, draft paper, or planned workflow is evidence that a DOI or release exists.
