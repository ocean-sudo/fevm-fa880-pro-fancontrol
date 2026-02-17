# Safety Policy

## Risks
- Overly low duty can cause thermal throttling or instability.
- Sudden sensor read failures can leave fans at stale values.
- BIOS/EC behavior may differ by firmware version.

## Default Guardrails
- `min_duty = 20` by default (avoid long-term `0%`).
- `failsafe_duty = 70` on read/write exceptions.
- Polling loop uses a short interval (`1.0s`) to converge quickly.
- Memory sensor missing: fallback to CPU sensor by default.

## Recommended Operating Practice
- Start with conservative curves, then tune downward.
- Stress test after any curve change (CPU and memory workloads).
- Keep `journalctl -u fevm-fan-curve.service -f` open during first runs.
- If behavior is abnormal, stop service and set static duty manually.
