# ADR 0034: A refused fetch is not an empty area

- Status: Accepted
- Date: 2026-08-06
- Deciders: swelter maintainers

## Context

Between 2026-06-19 and 2026-08-06, every Sensor.Community fetch swelter made returned nothing, and
nothing anywhere reported a problem. The live map served CAMS model data with zero physical
community sensors for seven weeks, the daily refresh workflow was green throughout, and the CLI
told operators `no readings (Sensor.Community is sparse outside Europe — try a EU area)`.

The mechanism, measured on 2026-08-06:

- `http.client` sends no `User-Agent` of its own, and `_request_json` passed the adapter's headers
  through unchanged. Every request went out anonymous.
- Sensor.Community declines an anonymous client. It does so with **`HTTP 200`** and the body
  `["\"error\": \"empty user agent not allowed\""]` — not a 4xx.
- `get_json` saw a success status and returned the document.
- `fetch` coerced it with `rows if isinstance(rows, list) else []`. The error document *is* a
  list, so it passed straight through.
- `parse_measurements` skips rows that are not objects, so it yielded nothing, without complaint.
- The CLI turned zero observations into a statement about the network's coverage.

The same request with an honest `User-Agent` returned 1,443 records from 613 live sensors in
Stuttgart, the network's origin city and swelter's default area.

Two things failed here, and only one of them is a missing header. The header was lost in
`a0be0aa` ("harden live open-data adapters for resilient daily refresh"), the commit that
centralised fetch/retry — hardening removed the thing that made the request legible. But the
outage lasted seven weeks because **absence and refusal were the same value**. Every layer below
the CLI had a defensible local reason to coerce, skip, or tolerate; the composition of those
reasons was a confident false statement about the world.

`tests/test_sources_http.py` pinned the behaviour rather than catching it: a test asserted that a
top-level `{"error": ...}` payload "yields nothing, no crash", and every other test stubbed
`_request_json` — the function where the header is built — so no test could observe whether a
request identified swelter at all.

## Decision

**Identify swelter on every request, and never let a refusal be reported as an absence.**

1. `sources/_http.USER_AGENT` is sent by default from `_request_json`, merged so a caller can
   still override it. This is politeness first — an operator watching that traffic can tell what
   it is and who to contact — and correctness second.
2. `sources/_http.expect_records(payload, *, source)` is the shared boundary between a served
   answer and a refused one:
   - `[]` returns `[]`. **An empty area is a real measurement and stays quiet.**
   - a non-empty list containing no objects raises `SourceError`, quoting what arrived.
   - anything that is not a list raises `SourceError`.
3. `sensor_community.fetch` uses it, so a refusal propagates as `SourceError` instead of an empty
   observation list.
4. The CLI states what it observed and stops asserting a cause it has not established.

The asymmetry in (2) is the decision, not an implementation detail: silence about an empty area is
honest, silence about a rejected request is not.

Implementation: `src/swelter/sources/_http.py`, `src/swelter/sources/sensor_community.py`,
`src/swelter/cli.py`. Acceptance evidence: `tests/test_sources_http.py` — a request-level test
asserting a non-empty `User-Agent` (which required testing below the `_request_json` stub, where
no previous test reached), and the exact 200-with-error-document payload raising end to end.

## Consequences

- Sensor.Community works again: 1,718 observations from 615 nodes on the first run after the fix.
- The other two live adapters (OpenAQ, Open-Meteo) now identify themselves too, since the header
  lives in the shared layer. Neither is known to have been affected; both are now legible.
- A refused fetch becomes a loud `SourceError` and a non-zero exit rather than a green run. The
  daily refresh workflow's `if/else` currently swallows an empty result — that is a separate gap,
  tracked in [#146](https://github.com/ChelseaKR/swelter/issues/146), and this ADR does not close
  it. **A raised error is only an improvement if something is listening.**
- `expect_records` is available to the other adapters and is the intended shape for any future
  source. It is deliberately narrow: it does not try to recognise error documents by content,
  only to refuse to read a non-record payload as records.
- Cost: an endpoint that legitimately returns a non-empty list of scalars would now raise. No
  current source does, and the alternative — guessing which non-record payloads are benign — is
  the failure this ADR exists to prevent.
- A superseding ADR is warranted if a source is added whose success payload is not a list of
  objects, or if we decide error-document detection should become content-aware.

### The general rule this is an instance of

A check that examined nothing must report *not checked*, never *no problems*. The same shape has
been found elsewhere in this portfolio in the same week — an empty fetch stored as a valid
baseline and reported "unchanged" forever, a fixity audit passing over zero packages, an
accessibility gate passing over zero documents, a partial API walk published as complete coverage.
Wherever swelter converts "we got nothing" into a statement about the world, that conversion needs
to be able to say "we do not know".
