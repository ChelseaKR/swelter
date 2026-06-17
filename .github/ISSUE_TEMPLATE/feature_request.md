---
name: Feature request
about: Suggest a change or addition
title: ""
labels: enhancement
assignees: ""
---

## Problem

What are you trying to do that swelter does not yet support? Describe the
situation, not just the feature.

## Proposed change

What you would like to see. If it touches the pipeline, say which stage
(nodes -> ingest -> qc -> calibrate -> aggregate -> serve/export) and which
module(s) under `src/swelter/`.

## Alternatives considered

Other approaches, and why they fall short.

## Hard-rules check

These are project invariants, not preferences. A request that breaks one will
be declined; please confirm the proposal holds them:

- [ ] No surveillance: adds no microphone, camera, Bluetooth, Wi-Fi client
      scanning, or per-device identifier, and adds no schema field that could
      hold a person.
- [ ] Privacy: keeps published coordinates grid-snapped unless the host opts
      into `precise`.
- [ ] Calibrated vs raw stay distinguishable; uncalibrated values stay marked
      provisional.
- [ ] Open and portable: keeps data CC0 and the export path first-class.

## Additional context

Links, references, or sketches.
