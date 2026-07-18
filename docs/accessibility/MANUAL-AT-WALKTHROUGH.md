# Manual assistive-technology walkthrough

Status: **pending execution for the expanded observatory**
Template last updated: 2026-07-16

This file is an execution record, not evidence that testing occurred. Do not change a pairing to
Pass without recording the tester, date, commit, browser/AT versions, task notes, findings, and links
to resolved defects.

## Required pairings

| Platform | Browser and assistive technology | Status |
| --- | --- | --- |
| Windows | Current Chrome + NVDA | Pending |
| Windows | Current Firefox + NVDA | Pending |
| macOS | Current Safari + VoiceOver | Pending |
| iOS | Current Safari + VoiceOver | Pending |

Also repeat the complete path with keyboard only, 200% browser zoom, and the operating-system
reduced-motion preference. Automated 320px, pseudolocale, target-size, focus, and reduced-motion
checks are supporting evidence; they do not replace these runs.

## Task script

1. Enter through the skip link; identify the page, Now, Explore, Network, and Data & method regions.
2. Change English to Spanish and back. Confirm the document language, names, dates, numbers, units,
   statuses, and errors are announced in the active language.
3. Search for a place, clear the search, and use the locate control without granting permission.
   Confirm both the denied and no-result states are understandable and focus does not move.
4. Change measurement and time. Play, pause, and stop playback by changing the time manually.
5. Focus the exposure braid. Use Left/Right Arrow and Home/End; then change both native history
   range controls. Confirm the selection status, summary, uncertainty, provisional count, and gaps.
6. Select a network-distribution row. Confirm the same place updates in Now, the active data view,
   evidence inspector, and shareable state without an unexpected focus jump.
7. Switch Map → List → Table with Tab and arrow-key tab navigation. Pan/zoom/reset the map without
   dragging, select a marker, read a full List item, sort both Table columns, and return to Map.
8. Read the evidence inspector, compare two places, save/update/remove a watch, and exercise copy or
   download controls. Confirm success/failure status messages are announced once.
9. Review network health, alerts, cooling-center text alternatives, source/calibration/uncertainty,
   license, offline copy, accessibility statement, and settings reset.
10. At 200% zoom and on iOS portrait/landscape, repeat the primary Now → braid → List/Table → evidence
    path with no lost content, clipped focus, two-dimensional page scrolling, or gesture-only task.

## Result record

| Field | Value |
| --- | --- |
| Tester | Pending |
| Date/time zone | Pending |
| Commit/release | Pending |
| Platform/browser/AT versions | Pending |
| Pairing | Pending |
| Tasks completed | Pending |
| Findings | Pending |
| Issue/patch links | Pending |
| Retest result | Pending |

When every pairing passes, update the [public statement](STATEMENT.md), [ACR](ACR.md), and folder
[README](README.md) in the same reviewed change. Preserve prior dated results rather than overwriting
their history.
