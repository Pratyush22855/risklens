# RiskLens Architecture

RiskLens is a small pipeline of single-purpose modules. Data moves in one
direction and every stage is testable on its own.

```
 data_generator.py        risk_engine.py + rules.py               reporting.py / visualization.py
+------------------+     +-----------------------------------+     +-----------------------------+
| Synthetic        |     | For each transaction (in time     |     | scored_transactions.csv     |
| transactions     | --> | order), using only PAST history:  | --> | flagged_transactions.csv    |
| (seeded, no real |     |   1. run every control            |     | risk_summary.json           |
|  data)           |     |   2. sum weighted points (cap 100)|     | PNG charts in docs/         |
+------------------+     |   3. map score -> decision        |     +-----------------------------+
                         |   4. build explanation            |
                         +-----------------------------------+
```

## Modules

| Module | Responsibility |
|---|---|
| `src/models.py` | `Transaction`, `RiskSignal`, `RiskAssessment`, `Decision`, and `UserHistory` (the behavioral baseline). |
| `src/rules.py` | `RuleConfig` (all weights/thresholds, with rationale) and one pure function per control. |
| `src/risk_engine.py` | `RiskEngine`: runs controls, sums points, applies thresholds, writes explanations, scores a whole DataFrame chronologically. |
| `src/data_generator.py` | Seeded synthetic users, normal behavior, and labeled anomaly scenarios. |
| `src/reporting.py` | Summary metrics and CSV/JSON output. |
| `src/visualization.py` | Matplotlib charts (Agg backend, PNG only). |
| `src/utils.py` | Paths and haversine distance. |
| `main.py` | CLI entry point that wires the stages together. |

## Design decisions

- **Rules are pure functions.** `(transaction, history, config) -> RiskSignal | None`.
  No hidden state, so each control has simple unit tests.
- **No look-ahead.** Transactions are sorted by time and each is scored before it
  updates the user's history.
- **Blocked events don't teach the baseline.** A BLOCKed transaction is counted as an
  *attempt* (so velocity still sees it) but does not add its device, country, or amount
  to the user's trusted profile. Otherwise an attacker's first blocked attempt would make
  the second look "normal".
- **Cold start is explicit.** Baseline controls (new device, new country, unusual amount)
  stay silent until a user has `min_history_for_baseline` trusted transactions. With no
  history there is nothing to compare against, and the design avoids scoring every first
  transaction as "new".
- **Additive, capped scoring.** Score = sum of triggered points, capped at 100. Additive
  scoring keeps the explanation a literal receipt: the listed points add up to the score.
- **One config object.** All weights and thresholds live in `RuleConfig`, so tuning is a
  reviewable one-place change rather than edits scattered through the logic.
- **The engine never reads the `scenario` column.** It exists in the synthetic data only so
  results can be inspected per scenario afterwards.
