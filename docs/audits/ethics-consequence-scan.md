# Ethics consequence scan

Status: implementation analysis current; named-human REVIEW-GATE signoff pending. Accountable owner:
Chelsea Kelly-Reif. Machine-assisted analysis: OpenAI Codex, 2026-07-16; this is not human review.
Owner release attestation remains blocked in `release-review-attestations.json`.

## Stakeholders and consequences

| Stakeholder | Intended benefit | Plausible harm or exclusion |
| --- | --- | --- |
| Residents in high-exposure neighborhoods | Timely, legible local evidence and a portable public record | A wrong, stale, model-derived, or provisional value is mistaken for individualized safety advice |
| Sensor hosts | Community evidence without exposing a home | Exact location or stable node identity narrows a host's address; open copies cannot be recalled |
| People represented by neighborhood context | Structural inequity becomes visible | Historical redlining, AC access, or canopy proxies stigmatize a place or are treated as causal/current facts |
| Disabled and Spanish-speaking residents | Equivalent access to findings and controls | Automated structural/catalog parity is mistaken for lived usability or accurate translation |
| Stewards | Repairable local infrastructure and auditable provenance | Operational/key/calibration burden falls on an under-resourced volunteer; stale data looks current |
| Journalists, researchers, agencies | Reusable export and traceable method | Source license, uncertainty, or sampling limits are stripped in downstream reuse |
| Original data providers | Wider legitimate use | Attribution/terms are lost during aggregation, especially in mixed OpenAQ artifacts |
| Bystanders/non-users | Better public heat/air decisions | Resource allocation follows an uneven sensor map, making unmeasured neighborhoods less visible |

## Worst plausible outcomes

- **Failure:** a resident relies on a stale/provisional reading or estimated WBGT and delays a
  protective action. The product therefore reports conditions and sourced context; it never says a
  person is safe.
- **Misuse:** a downstream publisher removes source, provisional, uncertainty, and license fields to
  present a block-level claim with false precision.
- **Privacy:** an exact host coordinate is published or a sparse public cell narrows a residence.
- **If the product works exactly as intended:** a confirmed-first ranking and better-calibrated areas
  receive more attention/resources, while under-instrumented neighborhoods remain provisional and
  less persuasive. Fairness review must treat missing confidence as a resource-allocation signal,
  not a reason to hide a place.

## Lines the product will not cross

- No microphone, camera, Bluetooth/Wi-Fi client scanning, person-shaped field, or individual
  tracking.
- No individual diagnosis, medical advice, evacuation order, regulatory-grade claim, or “safe now”
  determination.
- No silent mixing of raw/provisional, calibrated, model-derived, and directly sensed values.
- No inferred sensitive demographic attributes and no current-neighborhood moral rating from
  historical/context proxies.
- No blanket CC0 claim over third-party data and no public illustrative cooling-center/context
  fixture represented as jurisdiction truth.

## Misuse resistance and rollback

Mechanical controls keep provenance, QC/calibration, uncertainty, source, and license adjacent to
the value; grid-snap host locations; omit missing context instead of inferring it; and exclude the
illustrative cooling-center layer from Pages. Share cards bake the provisional/time-window caveat
into pixels.

If harmful publication occurs, stop/redeploy the affected static route, preserve its manifest and
workflow evidence, rotate compromised node credentials, and publish a corrected snapshot with an
incident note. A host can return future data to coarse mode, but already downloaded open copies may
be irreversible. Exact steps are in [`../runbooks/operations.md`](../runbooks/operations.md).

## Success measures and owner

Owner: Chelsea Kelly-Reif for the reference implementation; the named data steward/collective for a
deployment. Success means zero person-shaped fields/surveillance capabilities; zero unlabeled
provisional/model values; every artifact has source/license provenance; every release has a current
fairness/DPIA/threat/residual-risk review; and harmful-publication rollback is tested/documented.

Last verified: 2026-07-16. Recheck cadence: every release and any new ranking, guidance,
notification, context layer, source, sensing capability, or public-health claim.
