# Data card: boundaries and contextual layers

These assets are not observation data and are never swept into the root CC0 dedication. Each
GeoJSON file carries a metadata object with its source, license, attribution, and last-verified date.

| Layer | Repository role | Source/term | Publication rule |
| --- | --- | --- | --- |
| California boundary/basemap | Filters OpenAQ jurisdiction and draws California context | U.S. Census Bureau TIGERweb; U.S. Government work | Keep vintage/simplification provenance; review annually |
| Tree-canopy sample | Exercises descriptive context plumbing | Project-authored illustrative sample labelled CC BY 4.0 | Synthetic/local demonstration only; replace with jurisdiction data and its terms |
| AC-access sample | Exercises LACE-shaped context | Illustrative sample; real target is U.S. Census LACE, public-domain U.S. Government work | Never describe the sample as measured local AC access |
| Historical-redlining sample | Exercises HOLC context | Illustrative sample shaped for Mapping Inequality; CC BY-NC-SA 4.0 metadata | Never infer a grade where no historical HOLC map exists; preserve noncommercial/share-alike terms |
| Cooling-center sample | Exercises validated overlay/list parity | Project-authored illustrative sample labelled CC BY 4.0 | Excluded from public Pages; production requires a current jurisdiction-verified facility list |

## Method and limitations

Context values join to published grid cells and remain descriptive—not causal explanations and not
features on an observation record. The exposure brief omits a sentence when a layer has no matching
cell. A source/date/license field is required for every published claim. Historical redlining is
historical context, not a current neighborhood rating; AC and canopy layers are coverage-limited
proxies; cooling-center status/hours can change faster than a daily environmental refresh.

## Maintenance

The data steward verifies the exact jurisdiction source before publication, records its retrieval
date and transformation, preserves its terms, and sets a source-appropriate freshness SLA. The
illustrative repository files must never be promoted by copying without that replacement review.

Owner: data steward. Last verified: 2026-07-16. Recheck cadence: each source refresh, provider-terms
change, jurisdiction change, and release.
