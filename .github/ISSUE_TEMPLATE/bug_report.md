---
name: Bug report
about: Report something that does not work as documented
title: ""
labels: bug
assignees: ""
---

## What happened

A plain description of the bug.

## What you expected

What the README or docs led you to expect instead.

## Steps to reproduce

1.
2.
3.

If it involves the pipeline, include the exact `swelter` subcommand
(ingest / qc / calibrate / aggregate / export / serve / demo / rebuild) and,
where possible, a minimal payload or `swelter demo` run that shows it.

## Environment

- swelter version (`swelter version`):
- Python version (`python --version`):
- OS:
- Install method (uv sync / wheel):

## Hard-rules check

- [ ] This report does not include exact node locations a host has not chosen
      to disclose (coords should be grid-snapped unless the host opted into
      `precise`).
- [ ] This report does not contain any data that identifies a person. The
      schema holds none; please do not add any in the issue.

## Logs / output

```
paste relevant output here
```
