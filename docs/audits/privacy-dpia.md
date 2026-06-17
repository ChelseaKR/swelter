# Data protection impact assessment: node-location risk

Last verified: 2026-06-16. Recheck cadence: each release, and whenever `models.py`, `config.py`,
or the published API surface changes.

This is the fuller data-protection impact assessment that audit C in
[../RESPONSIBLE-TECH-AUDITS.md](../RESPONSIBLE-TECH-AUDITS.md) references. It exists because the
one residual privacy risk in swelter is not in the measurements — those are aggregate
environmental readings with no personal data — but in *where a sensor sits*. A node lives on
someone's porch, fence, or balcony. A precise published coordinate for that node is, in effect, a
pointer at a host's home. This DPIA works through that risk and the mitigation in the code.

It follows the shape of a GDPR Article 35 DPIA (processing description, necessity and
proportionality, risks to individuals, mitigations, residual risk) without claiming GDPR
applicability: swelter is an independent open-source reference implementation, not a controller
operating a live network. A collective that deploys it is the controller and should adapt this
assessment to its jurisdiction and its hosts.

## 1. Processing described

| Question | Answer |
|----------|--------|
| What is processed | Aggregate environmental measurements: temperature, humidity, PM2.5, PM10, NO2, derived heat index. One value per parameter per node per timestamp. |
| Personal data fields | None. The `Observation` dataclass (`src/swelter/models.py`) has fields `node_id`, `timestamp`, `parameter`, `value`, `unit`, `calibration`, `qc`, `uncertainty`. There is no name, device id, MAC, owner, account, or precise person-coordinate field, and the schema is frozen so one cannot be added at runtime. |
| Indirect identifiers | A node's *location*, held in config (`network.yaml`), not in the observation record. This is the entire subject of this DPIA. |
| Lawful basis (for a deployer) | The hosting collective's own siting decision; precise disclosure is opt-in per host. swelter never requires a precise coordinate. |
| Retention | Observations are append-only and intended to be kept (open environmental history, CC0). Location precision is a config choice a host can change at any time. |

The measurements themselves carry essentially no privacy risk: the air temperature on a block is
not personal data, and the data is published CC0 on purpose. The assessment below is therefore
entirely about the node-location indirect identifier.

## 2. Necessity and proportionality

The network needs *some* location per node, because a heat-island and AQI map with no geography
is useless — block-scale exposure is the question. It does **not** need a precise location to do
that job. A reading attributed to a ~150 m grid cell maps urban heat just as well as one
attributed to a rooftop, because heat-island and AQI gradients are a neighborhood-scale
phenomenon, not a per-address one. Coarse location is therefore both sufficient for the purpose
and the proportionate choice, which is why it is the default.

## 3. Threat model for node location

Assets at risk: the home address (or close approximation) of a person who volunteered to host a
sensor. Hosts in frontline neighborhoods — the people swelter is built for — may have specific
reasons to not want their address inferable from a public map (housing precarity, harassment,
immigration status). The risk is concrete, not theoretical.

| Threat | Vector | Without mitigation | With mitigation |
|--------|--------|--------------------|-----------------|
| Re-identification of a host's home | Precise published coordinate read off the public map or the SensorThings `Things` endpoint | A pin within metres of a front door | Published coordinate is the centre of a ~150 m grid cell; the precise value never leaves config |
| Triangulation across endpoints | Cross-referencing the map, the API, and the export | Same precise point in every surface | Every public surface reads `public_location()`; there is no second, finer coordinate to leak |
| Correlation with the calibration record | A node co-located at a known reference monitor, inferring its home from the monitor's location | A node's home guessed from its training window | The reference monitor location is a separate public asset (a regulatory station); co-location does not publish the node's home |
| Inference from a single-node cell | A grid cell containing exactly one node | "this cell = this person" if the cell is sparse | Grid resolution is a deployer choice; a collective in a low-density area can widen it, and the precise value is still never published |
| Future schema creep | A PR adding a precise-coordinate or owner field to the observation record | A person enters the data | Frozen schema + the "a PR adding such a field fails review" rule (hard rule 1); audit C item is review-gated |

## 4. Mitigation in the code (the grid-snap)

The mitigation is not a policy promise, it is a function. `config.public_location()` is the only
coordinate the rest of the system is allowed to read:

```python
def public_location(self, grid_m: float) -> tuple[float, float] | None:
    if self.lat is None or self.lon is None:
        return None
    if self.location == "precise":
        return (self.lat, self.lon)
    return snap_to_grid(self.lat, self.lon, grid_m)
```

`snap_to_grid` returns the centre of a `grid_m`-sided cell (default 150 m; longitude step widens
with latitude so cells stay roughly square on the ground). The default `location` is `"coarse"`;
a host gets a precise pin only by explicitly setting `location: precise` in `network.yaml` —
opt-in, not opt-out. The API's `things()` builder reads `config.public_locations()` and so can
only ever emit the snapped point. The dashboard, the GeoJSON surface, and the export all read the
same path. There is no code path that publishes `node.lat` / `node.lon` directly.

This is verifiable, and it is verified: the snap behaviour and the opt-in default are covered by
the test suite (`make test`), and the absence of a PII field in the schema is held by the type
gate (`make typecheck`) and the schema tests. Both run on every PR.

## 5. Residual risk

- **A host who opts into `precise`.** If a host deliberately sets `location: precise`, their exact
  pin is published. This is by design — exact node locations are the host's to disclose (hard
  rule 2) — but it shifts the risk onto an informed choice. A deploying collective should make the
  consequence of opting in plain to hosts. swelter's job is to make coarse the default and precise
  a conscious act, which it does.
- **Sparse single-node cells.** In a low-density deployment a 150 m cell may contain one node, so
  the cell still roughly localises that node. The grid does not claim k-anonymity. The mitigation
  is a deployer choice — widen the grid — plus the fact that even a sparse cell is a 150 m square,
  not a doorstep.
- **Out-of-band disclosure.** A host who tells neighbors which sensor is theirs, or whose enclosure
  is visible from the street, defeats the grid. swelter cannot mitigate disclosure it does not
  control; it can only guarantee the *published data* does not do the disclosing.

## 6. Conclusion

The processing is low-risk on the measurements (no personal data, frozen schema) and carries one
real indirect-identifier risk in node location, mitigated by a default-coarse, opt-in-precise grid
snap enforced in code and tested in CI. The residual risk is dominated by informed host choices
and out-of-band disclosure, which sit with the deploying collective. No further technical
mitigation is required for the default configuration; the review-gated item in audit C exists to
keep it that way as the code evolves.

---
Reviewed by: Chelsea Kelly-Reif, 2026-06-16. swelter is an independent personal open-source
project; a deployer is the data controller and should re-run this assessment for its own context.
