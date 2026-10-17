# ADR 0056: Open-Meteo access is separate from its data license, and an API key reaches only Open-Meteo

- Status: Proposed
- Date: 2026-10-17
- Deciders: Chelsea Kelly-Reif

## Context

The CAMS/Open-Meteo source card said "Terms: CC BY 4.0 as documented by Open-Meteo for this use".
That is the data license, and it is correct. It is not the whole of Open-Meteo's terms. As of
2026-10-17, those terms separate the license on the *data* (CC BY 4.0, which allows commercial reuse
with attribution) from the conditions for *calling the API*. The free, keyless hosts are for
non-commercial use only and are rate-limited: fewer than 10,000 calls a day, 5,000 an hour, and 600
a minute. Commercial use needs a paid API subscription. That subscription comes with a key for
separate customer hosts (`customer-api.open-meteo.com`, `customer-air-quality-api.open-meteo.com`),
which take the key as an `apikey` query parameter. Merging the two left a reader to conclude that
CC BY 4.0 alone made any deployment's fetch permissible. The details and their verification are in
[`docs/data-cards/openmeteo-cams.md`](../data-cards/openmeteo-cams.md#distribution-and-license).

The adapter hard-coded the free hosts, so a deployment that needs the commercial tier could not use
swelter without patching it. Adding a key adds a new credential to the fetch path. This is the
second provider credential, after OpenAQ's. Open-Meteo puts it in the URL rather than in a header,
and the shared fetch quotes the URL in every `SourceError` message, which the CLI prints to stderr
and CI logs retain.

## Decision

1. **State data license and API access separately** in the source card, `DATA-LICENSE`, and the
   adapter's `LICENSE` comment. The published data license string
   (`CC BY 4.0 (Copernicus CAMS via Open-Meteo)`) and attribution do not change: the access tier
   does not change the data's terms.
2. **An optional key selects the customer hosts.** `swelter.sources.openmeteo.fetch(api_key=...)`
   uses the customer hosts and appends a percent-encoded `&apikey=` when it gets a key. The CLI
   reads the key from `OPENMETEO_API_KEY`, following the `<PROVIDER>_API_KEY` convention of
   `OPENAQ_API_KEY` and `AIRNOW_API_KEY`. A blank or unset variable means no key. With no key, the
   adapter makes exactly the free-host requests it made before key support existed.
3. **The key reaches Open-Meteo and nothing else.** `swelter.sources._http.redact_url` replaces the
   value of credential-named query parameters in every URL the shared fetch quotes into an error.
   `openmeteo.scrub` is a second guard on the adapter's and CLI's own failure lines. The key is not
   logged, printed, stored, cached, written into `network.yaml`, the store, sidecars, or any
   published artifact, or recorded as provenance. `swelter doctor` reports whether
   `OPENMETEO_API_KEY` is set and never reports its value.
4. **The reference deployment stays keyless.** No workflow change is made. The owner decides,
   with Open-Meteo, whether the reference site's posture fits the free tier. The open items are
   listed on the source card.

Acceptance evidence: F-14 in [`docs/ACCEPTANCE-TEST-MAP.md`](../ACCEPTANCE-TEST-MAP.md), through
`tests/test_openmeteo_access.py`.

## Consequences

- A commercial or contracted deployment can comply by setting one environment variable, with no code
  change. The data's license, attribution, raw/provisional state, and caveats are unchanged on both
  tiers.
- The default path is unchanged byte for byte, so the reference site and existing stores are not
  affected.
- Credential exposure is a new disclosure risk on the fetch path. The threat model, data-flow
  inventory, DPIA, and `SECURITY.md` now list the Open-Meteo key beside the OpenAQ key. Redaction
  covers the shared fetch's own messages. A future adapter that puts a credential somewhere other
  than a credential-named query parameter must add its own guard and test.
- swelter does not check whether a deployment's use is commercial. That is a legal and operational
  judgment for the operator, not something code can detect. The doctor line and the source card name
  the condition so it is not missed.
- Open-Meteo may change its terms, host names, or limits; its terms say changes take effect when
  posted. If the customer-host scheme or key parameter changes, write a superseding ADR together
  with the adapter change.
