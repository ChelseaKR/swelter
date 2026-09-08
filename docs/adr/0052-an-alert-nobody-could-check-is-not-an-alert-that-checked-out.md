# ADR 0052: An alert nobody could check is not an alert that checked out

- Status: Accepted
- Date: 2026-09-07
- Deciders: swelter maintainers

## Context

Calibration publishes evidence for *values* (ADR 0002): every corrected reading names the fit
behind it, its window, its residual and its reference. Nothing published evidence for *alerts* —
and an alert is the loudest claim swelter makes. It goes onto a lobby card (`swelter cards`), into
an Atom feed, and in front of a resident deciding whether to go outside. A collective handing that
to a public-health partner (#229) will be asked how often it was wrong, and the honest answer was
that nobody had ever checked.

The check is available. A reference-grade monitor reports for the same hour and, sometimes, near
enough to the same place; `colocate` already pairs a node against one to fit a correction. The same
pairing can be pointed at a published alert instead of a training window, and the alert then has an
outcome: the reference agreed, the reference disagreed, or there was no reference.

That third outcome is where an accuracy metric goes wrong, and it is why this needs a decision
rather than an implementation.

## Decision

### 1. Unverifiable is a first-class outcome, and is never a score

An alert with no reference reading in range was not confirmed and was not contradicted. It was not
checked. It is counted in its own column, excluded from the precision denominator, and when a
parameter has **no** scored alerts at all the precision field is `null` with the reason stated in
words — never `0.0`, and never `1.0`.

Both wrong answers are available and both are worse than none. Folding unverifiable alerts into the
denominator publishes `0.0` and reads as "every alert this network raised was wrong". Dropping the
parameter from the report entirely hides the largest class of unchecked claim. Publishing a rate
over an empty denominator is the defect ADR 0037 exists to prevent, wearing an accuracy metric's
clothes.

Measured, not argued: with the denominator changed to include unverifiable alerts, the suite
reports `precision=0.0` over three alerts nobody checked, and two tests catch it.

### 2. Five reasons, kept apart, because they send a steward somewhere different

An `unverifiable` verdict names which of these applies:

| reason | what a steward does about it |
| --- | --- |
| no reference reading in the run is for this parameter | nothing — AirNow measures no heat index; this hazard has no regulatory counterpart |
| readings for the parameter exist, but from no monitor the network declares | fix `reference_monitors`; this is a configuration error, not a coverage gap |
| the nearest declared monitor publishes no coordinate | add the station coordinate; it is public record |
| no monitor is within the distance bound | site or licence a closer feed, or widen the bound deliberately |
| a monitor is in range but published nothing that hour | nothing, or a different reference feed |

The third one is separated for a specific reason. Defaulting a missing `lat`/`lon` to `0, 0` puts
the monitor in the Gulf of Guinea and rules it out on distance — which publishes "checked, too far"
over "we do not know where it is". That mutation was run: the reason text changes from *unknown
rather than zero* to *no reference monitor within 10000 m*, and the test catches it.

### 3. The crossing test is the shipped one, not a copy of it

A historical alert is `alerts.crossing` applied to a stored cell — the same function the live feed
and `exposure_brief`'s danger-day count call. The reference reading is put through that same
function, on a cell differing only in its value.

Re-deriving "what counts as Danger" here would let the audit and the feed drift apart silently, and
the audit would then be scoring a threshold nobody ships. Substituting a plausible-looking direct
comparison of the reference concentration against the AQI floor turns confirmed alerts into
contradicted ones; two tests catch that too.

### 4. Recall is not measured, and the document says so

The audit reports precision only. Reference coverage is far too sparse to say how many real
episodes the network failed to alert on, and a precision table published on its own would be read
as the whole picture. The rendered report carries that sentence in a "What this audit does not say"
section rather than leaving it to a reader to infer.

### 5. The distance and time bounds are swelter's own, and say so

No published rule states the distance at which a regulatory PM2.5 monitor stops representing an
airshed — it depends on terrain, sources and the day's meteorology. The default (10 km, and the
30-minute pairing tolerance `colocate` already uses) is a parameter for exactly that reason, every
run records the values it used, and the report names them as swelter's own rather than attributing
them to a standards body that never set them. This is the same discipline ADR 0050 applied to the
smoke pack's three-cell minimum.

### 6. The audit never changes a threshold, and a contradiction is not a tool failure

It is evidence for a steward, not a controller. A contradicted alert exits `0`, because a caller
gating on `$? -eq 0` must not be told that an audit which reported contradictions did not happen.
Exit `1` is reserved for the audit not running — including when no `--reference-fixture` is given,
which is refused outright rather than producing a report in which every alert is unverifiable and
which looks like it checked something.

## Consequences

A collective can answer "how often was it wrong" with a document, and can see at a glance how much
of its alerting is unchecked — which, for a network with no nearby regulatory monitor, will be all
of it. That is the honest picture and it is itself the finding: run against the bundled demo with
the committed AirNow fixture, all 25,774 alerts come back unverifiable, because the fixture's
monitor id is not one `network.yaml` declares. The report says exactly that, in the sentence
reserved for it.

The costs: the audit is only as good as the reference series it is handed, and a fixture is an
operator responsibility. It scores the *current* pack's floors against *historical* readings, so a
pack whose thresholds changed mid-window is scored against today's — each alert row carries the
calibration **method** and the reference it was fitted against, verbatim from the cell, so a
contradiction can still be traced to how the value was produced, but a per-hour pack history would
need the pack version to be recorded on the surface, which it is not. The row carries methods and
not correction *version ids* because that is what the surface publishes; an earlier draft of this
field claimed versions and re-split the cell's joined method string on the wrong separator, so it
neither split nor said what it held.

A control on that correction is worth recording, because it did not behave as expected.
Re-introducing only the wrong separator — `", ".join(method.split(", "))` — leaves the suite
**green**: that round-trip is the identity on any string not containing `", "`, so the separator
error is unobservable in isolation. Only restoring the field's original *shape and name* (a tuple
published under a key claiming versions) turns the guard red. The first run is the honest
measurement, and the lesson is that the defect here was never the split — it was publishing a
value under a name for something else.

A superseding ADR is needed if recall becomes measurable (a denser reference network, or a
different reference source), if the audit is ever wired to change a threshold, or if pack versions
become part of the stored surface so a historical alert can be scored against the floors that
actually raised it.
