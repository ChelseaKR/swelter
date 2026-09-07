# ADR 0051: A catalog record carries the manifest's digests, or it is not written

- Status: Accepted
- Date: 2026-09-07
- Deciders: swelter maintainers

## Context

`swelter snapshot` freezes a citable release (ADR 0006, ADR 0024) and `swelter reproduce` proves
its surface can be re-derived (ADR 0049). What neither produces is a *catalog record*: the
descriptor a CKAN instance (`data.ca.gov`) or a Socrata portal harvests before a dataset is
findable by anyone who was not sent the link. `docs/AGENCY-COMPLIANCE-PACK.md` promises an agency
partner can take the data with them; today that means a CSV and a JSON file, and a portal cannot
ingest either without a record describing it.

The two descriptors those portals read are a Frictionless Data Package (`datapackage.json`:
resources, a Table Schema, licences, per-resource digests) and a DCAT record (`dcat:Dataset` with
one `dcat:Distribution` per file). Generating them is mechanical. Generating them *honestly* is
not, because a harvested record is republished by the portal as fact about the dataset, under the
portal's name rather than swelter's, to readers who will never open the snapshot it came from.

Four decisions in this generator are the difference between a catalog entry and a laundered claim.

## Decision

### 1. The digests are the manifest's, verified before anything is written

Every file the package republishes is read out of the snapshot and its SHA-256 compared against
the value already recorded in `MANIFEST.json`. A mismatch refuses the whole operation, by
filename, and writes nothing.

Recomputing the digest on the way past would have been one line shorter and would have handed a
tampered snapshot a clean, portal-ready record whose checksum agreed with the tampering. The
verification is the point of the exercise: a catalog record is a claim that these bytes are that
release, and swelter is only entitled to make it where the release's own manifest already did.

A manifest that lists no files is refused for the same reason `reproduce` refuses one: every
verification below it is a lookup into that list, so an empty list would make each of them pass
over a file nobody had checked.

### 2. The package directory is self-contained, and the copies inherit the verification

Frictionless resource paths may not escape the package root, so the snapshot's data files are
copied into the package rather than referenced with `../`. The duplication is deliberate and is
only acceptable because of decision 1: each copy is written from bytes that were verified against
the manifest in the same call, so the second copy carries the release's integrity claim instead of
starting an unverified fork of the data.

### 3. A per-location source is described, not flattened to an SPDX identifier

Hard rule 6 keeps third-party terms source-specific, and OpenAQ redistributes other providers'
data under terms that differ location by location. A `licenses` array is exactly the shape that
invites those to be collapsed into one identifier, and a harvester would then publish that
identifier as the grant under which the whole dataset may be reused.

So only licence strings this project can map with certainty (`CC0-1.0`, `CC-BY-4.0`, `ODbL-1.0`)
get an SPDX `name`. Anything else is published as the snapshot's own licence *statement* in
`title`, with `path` pointing at the retained `source-license-ledger.json` — the per-location
evidence, in the package, where a reuser can read it.

### 4. Absence stays absent, and a measured empty set stays a measurement

The Table Schema declares `missingValues: [""]`, so a portal preview renders an unmeasured
`uncertainty` as a gap rather than as zero (ADR 0037, F-28).

But `qc_flags` overrides that to `[]`. An empty cell in that column means QC ran and found nothing
suspicious — a completed check with an empty result — and the table-wide rule would have published
it as a check nobody performed. That is the same defect as a failed read counted as a zero,
pointing the other way, and it is why the descriptor declares Frictionless **v2** (`$schema`)
rather than the older `profile: tabular-data-package`: v2 is where `missingValues` may be set per
field, and under v1 a single table rule has to serve both columns.

The same rule governs the rest of the record. A release whose manifest records no observation
window gets no `dct:temporal` at all, not an interval with null endpoints a portal would render as
a range. Without a `--base-url` no distribution carries a `dcat:accessURL`, and the record says so
in `swelter:note` instead of inventing a host.

### 5. The Table Schema is generated from the data dictionary and refuses to guess

Fields come from `dictionary.build_data_dictionary()` in the exact column order
`export._CSV_FIELDS` writes, so the schema and the file it describes cannot disagree about which
columns exist or what order they are in. A CSV column that the dictionary does not describe, and
that is not one of the two declared export-only provenance columns, raises rather than being
emitted with an empty description: a schema that silently omitted a column would tell a portal the
file is narrower than it is, and every row after the omission would be misparsed.

### 6. The record is dated from the snapshot, and tagged `en`

`dct:issued` and `created` are the snapshot's own `created_at`, never the wall clock, so two
packagings of one release are byte-identical — including across processes under different
`PYTHONHASHSEED` values, which is the only way the claim can honestly be measured.

`dct:title` and `dct:description` are language-tagged `en`. swelter has no independently reviewed
Spanish catalog text (#106), and an untagged string would let a Spanish-language portal present
English prose as its translation of the dataset's name.

## Consequences

An agency partner can hand a portal a directory. The record names the data-schema version it was
written against (`dct:conformsTo`), carries a checksum per distribution, and states its temporal
extent when the release has one.

Nothing is pushed anywhere. `swelter package` writes files; publishing to a portal API is an
operator action with its own credentials and its own accountability, and is out of scope here and
in the issue that asked for this.

The costs are two. The package duplicates the snapshot's bytes, which is why decision 2 ties the
copies to decision 1's verification rather than treating duplication as free. And the descriptor
is generated against the Frictionless v2 profile: it was validated with `frictionless` 5.19.0
against the bundled demo release — 151,812 rows, `VALID`, with a deliberate mid-file type error
and a byte-level edit both reported — but that library is not a project dependency, so the
validation is a recorded measurement rather than a standing merge gate. Adding it as a gate needs
its own dependency and supply-chain review; #243 tracks that remainder.

A superseding ADR is needed if swelter ever publishes to a portal API directly, if a resource is
added that the manifest does not cover, or if a reviewed Spanish catalog makes a bilingual record
honest.
