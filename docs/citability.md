# Citability and archival

Software and data are cited separately because they have different versions, provenance, and rights.

Owner: Chelsea Kelly-Reif. Last verified: 2026-07-16. Recheck cadence: every release, snapshot-schema
change, or Zenodo/JOSS requirement change.

## Cite the software before a release DOI exists

Use [`CITATION.cff`](../CITATION.cff) and identify the exact commit. The repository currently prepares
version `0.1.0`, but there is no released date or DOI until an annotated tag and GitHub Release exist.

Suggested form:

> Kelly-Reif, C. (2026). *swelter* (0.1.0 release candidate, commit `<sha>`) [Computer software].
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
3. Create the annotated `v0.1.0` tag from the verified merge commit. Let the release workflow build,
   verify, sign, attest, and publish the artifacts.
4. Confirm Zenodo archived the GitHub Release and issued a version DOI and concept DOI.
5. Add the concept DOI to `CITATION.cff` in a follow-up change and cite the version DOI for that exact
   release where reproducibility matters.
6. Update any JOSS draft against the tagged source and submit only when the maintainer can support the
   review/maintenance commitment.

## Repository artifacts

| Artifact | Current role | Release requirement |
|---|---|---|
| `CITATION.cff` | Software citation metadata for GitHub and tools | Version matches tag; add real release date and DOI when available |
| `.zenodo.json` | Zenodo deposit metadata | Must match software metadata and source-specific rights wording |
| `CHANGELOG.md` | Human-readable release history | Dated section for the tag, with no fabricated earlier release |
| `paper/paper.md` / `paper/paper.bib` | Draft publication material | Re-verify claims, references, version, and evidence against tagged source |
| Snapshot citation/manifest | Dataset-specific citation and integrity evidence | Generated from the exact store/source set; terms/attribution retained |

No metadata file, badge, draft paper, or planned workflow is evidence that a DOI or release exists.
