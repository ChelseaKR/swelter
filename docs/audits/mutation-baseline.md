# Core safety mutation baseline

Evidence date: 2026-09-06.
Tool: mutmut 3.7.0 (exactly locked in `uv.lock`).

Score: **92.09%** killed / all generated mutants; floor: **80.00%**.

| Status | Count |
|---|---:|
| killed | 1584 |
| survived | 136 |

The JSON evidence beside this file binds the result to SHA-256 hashes of every
mutated source file and selected test, the canonical mutmut configuration, and the
exact mutmut lock entry. `make mutation-baseline-check` fails when any input changes.
