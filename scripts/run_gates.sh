#!/usr/bin/env bash
# Run every make target named on the command line, and report each one's result.
#
# Why this exists. The aggregate gates used to be prerequisite lists, and make
# stops a prerequisite list at the first failure. That is the right behaviour
# for a build, where step 4 needs step 3's output, and the wrong behaviour for
# a gate set, where the checks are independent: one unfixable dependency
# advisory in the npm toolchain meant OSV-Scanner failed and semgrep, the
# secret scan, and the workflow policy check then never ran at all -- silently,
# because a red job looks the same whether it ran one gate or six.
#
# So every gate runs, whatever the gates before it did. That is not the same as
# tolerating failure: each gate prints its own PASS/FAIL, and this script exits
# non-zero if any of them failed. Nothing is suppressed and nothing hides
# behind anything else's result.
set -uo pipefail

make_bin="${MAKE:-make}"
status=0
failed=()

for gate in "$@"; do
  printf '\n== make %s ==\n' "$gate"
  if $make_bin --no-print-directory "$gate"; then
    printf '== %s: PASS ==\n' "$gate"
  else
    status=1
    failed+=("$gate")
    printf '== %s: FAIL ==\n' "$gate"
  fi
done

printf '\n'
if [ "$status" -eq 0 ]; then
  printf 'all %d gates passed: %s\n' "$#" "$*"
else
  printf 'FAILED %d of %d gates: %s\n' "${#failed[@]}" "$#" "${failed[*]}" >&2
fi
exit "$status"
