# Benchmarks

Benchmark across heterogeneous seeded faults, not one happy-path demo. Suggested categories: software logic, database, frontend, security, ML, dependency/configuration, performance, robotics, and research reproduction.

Primary metric: **Verified Autonomous Task Completion Rate**.

Reliability metric: **False PASS Rate**, target 0.

Also record project-understanding rate, specialist-selection accuracy, root-cause accuracy, regression rate, human interventions, iterations, elapsed time and model/token usage. `office benchmark --input results.json` aggregates the result schema implemented in `engineering_office.benchmark`.
