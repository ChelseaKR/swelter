# Operations runbook

Use this when the public artifact is stale, unavailable, incorrectly sourced, or when a self-hosted
network may have accepted forged data. The first goal is to stop new harm; preserving evidence comes
before deleting or rewriting anything.

Owner/escalation: repository maintainer for the reference Pages site; the local steward and hosting
collective for a community deployment. Security reports follow [`SECURITY.md`](../../SECURITY.md).

## Triage in five minutes

1. Record UTC time, affected route, visible source, data hour, and a screenshot or saved response.
2. Inspect the route's `demo.json`, `DATA-LICENSE`, `publish-manifest.json`, and
   `sample-health.json`. They identify the selected provider, terms, artifact hashes, and freshness.
3. Check the latest `demo` workflow and the commit it deployed:

   ```console
   gh run list --repo ChelseaKR/swelter --workflow demo --limit 10
   gh run view RUN_ID --repo ChelseaKR/swelter --log-failed
   ```

4. Classify the symptom: availability, stale data, wrong geography/source/license, misleading
   calibration/provisional state, leaked precise host location, or forged write-path data.
5. If a resident could make a harmful decision from the artifact, stop or replace the publication
   before debugging convenience features. Do not delete the source store or run destructive git
   commands during triage.

## Static Pages failure

- **Fetch failed but fallback is truthful:** leave the fallback live, confirm `demo.json` and the UI
  identify it, and investigate the provider separately.
- **Artifact/source/license mismatch:** treat as a publication integrity incident. Disable the
  affected deploy path or deploy the last known-good commit; preserve the failed workflow log and
  generated manifest. Never relabel third-party data as CC0 to keep the site up.
- **Stale data:** the UI must show its observation hour and stale caveat. Re-run the workflow only
  after the upstream provider and artifact terms are understood; repeated blind retries can publish
  an older restored store as if it were fresh.
- **Wrong geography or illustrative context:** take the affected overlay/route out of publication
  and forward-fix. The repository's illustrative cooling-center/context fixtures are not production
  jurisdiction data.

Rollback is a new deployment of a known-good commit, not a mutation of the already-published
artifact. After rollback, verify both `/` and `/sensors/`, their route-scoped service workers, source
labels, data hours, license links, selection deep links, and exported CSV.

## Forged or compromised node ingestion

1. Stop `swelter ingest-serve`; keep the read-only public surface separate and available only if its
   existing data remains trustworthy.
2. Copy the store, quarantine, manifest, digest, keys-file metadata (not key values), and logs to a
   restricted evidence location.
3. Rotate the affected node key with `swelter node-key NODE_ID --keys node-keys.yaml`, provision the
   new key directly to that node, and restart the listener only after the old sender is excluded.
4. Identify the suspect window from authentication/quarantine records and observation provenance.
   Raw rows are append-only; do not silently overwrite them. Publish a corrected derived snapshot
   with an incident note or start a clean store according to the collective's governance decision.
5. Re-run archive verification and the full quality gate before republishing.

## Precise-location exposure

1. Remove the affected route/config from further publication and contact the host privately.
2. Switch future publication to `location: coarse`, confirm with `swelter node-preview`, and rebuild.
3. Explain the hard limit: already downloaded open artifacts and third-party caches cannot be
   recalled. Record the host's choice and the response in the governance log without publishing more
   identifying detail.
4. Update the DPIA and residual-risk register; treat recurrence as a release blocker.

## Backup and restore drill

Run this quarterly, and after any change to ingest, the store layout, or the source terms. It
needs no engineer: every step is one command and prints its own verdict.

1. **Take a backup.** `swelter backup --store store --out backups/$(date -u +%Y-%m-%d).tar`
   It refuses an empty store, a store with an open SQLite journal, and a store whose
   `source-metadata.json` is present but unreadable. A refusal is the drill working.
2. **Rehearse the restore without touching the live store.**
   `swelter restore backups/<file>.tar --verify-only --receipt drills/<date>.json`
   This extracts to a temporary directory, checks it, prints the receipt, and writes no store.
3. **Read the receipt, including the third column.** It reports `PASS`, `FAIL` and
   `NOT_APPLICABLE`. `NOT_APPLICABLE` is not a pass: "the store had no corrections.yaml when it
   was archived" means there was nothing to compare, and if you expected a correction registry to
   be there, that line is a finding. The verdict is `verified` only when all six required checks
   ran and passed.
4. **Restore for real only when you need to.**
   `swelter restore backups/<file>.tar --store store-restored --verify`
   A failed verification writes nothing, so the target is left exactly as it was. `--force` is
   required to replace a non-empty directory.
5. **Confirm the restored store independently.**
   `swelter verify-archive --store store-restored` and `swelter doctor --config network.yaml`.
6. **Apply retention.** `swelter backup --prune backups --keep 4 --dry-run`, read the plan, then
   run it without `--dry-run`. If it refuses, an archive on that shelf cannot be verified: fix or
   remove that archive before pruning anything, because a shelf you cannot read is not a shelf
   you should be deleting from.

Keep the receipts. Two backups of an unchanged store are byte-identical and so are two receipts
for the same archive, so a receipt that differs from last quarter's means something actually
changed.

Encryption at rest is not provided: the tarball is plain, and where it is stored is the
collective's decision. Store it somewhere with the same access control as the store itself.

## Recovery verification

- `make verify` passes at the recovery commit.
- The backup drill above completes with a `verified` verdict on the most recent archive.
- The artifact manifest hashes every emitted file and source/license claims agree across UI,
  `demo.json`, export, and `DATA-LICENSE`.
- Both route-scoped workers serve the new release and no older owned cache remains active.
- The latest observations are clearly fresh or clearly labelled stale/provisional.
- An incident issue records start, containment, recovery, cause, and follow-up; its timestamps feed
  the DORA recovery metric.

Last verified: 2026-07-16. Recheck cadence: each release, after every incident, and whenever ingest,
publication, caching, source selection, or rollback mechanics change.
