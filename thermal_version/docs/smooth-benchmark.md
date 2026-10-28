# Smooth-control SIL results (2026-09-22)

Assumed first-order motor; NOT hardware measurements. Angles in degrees. Seed 42.

| Scenario | Tracking RMSE old / new | Reference acceleration RMS old / new | Simulated motor acceleration RMS old / new |
| --- | --- | --- | --- |
| static_noisy | 1.086 / 0.994 | 12.388 / 2.510 | 4.842 / 3.902 |
| static_slow_motor | 1.475 / 1.118 | 17.175 / 2.354 | 3.148 / 2.002 |
| moving | 1.751 / 1.430 | 26.678 / 3.785 | 10.152 / 8.109 |
| moving_low_fps | 2.231 / 1.508 | 27.285 / 4.125 | 7.839 / 5.828 |
| dropout | 1.824 / 1.498 | 25.743 / 5.425 | 9.414 / 8.396 |
| near_limit | 4.235 / 4.632 | 12.813 / 3.673 | 6.948 / 6.614 |
| slow_precision | 4.743 / 2.569 | 0.336 / 0.174 | 0.000 / 11.895 |
| center_noise | 0.287 / 0.492 | 4.956 / 0.680 | 2.443 / 1.339 |

Acceleration RMS units: deg/s^2. A smaller value indicates less acceleration variation in this specific simulation, not universal smoothness.

Tradeoffs: near-limit tracking RMSE increases because braking starts earlier. Center-noise residual error increases while micro-corrections decrease. Slow-precision motor acceleration rises from zero because the old controller was completely stalled by quantization. No claim that every metric improves.

Run tools/benchmark_servo.py for all CSV traces and report.json; tools/plot_servo.py generates comparison.png/svg. Moving scenarios additionally pass seeds 7 and 123.
