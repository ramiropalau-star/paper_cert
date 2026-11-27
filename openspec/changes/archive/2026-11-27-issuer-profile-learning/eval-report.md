# Extraction evaluation report — issuer-profile-learning

Golden set: `default` v1 (7 cases, built from approved/validated certificates).
Model: `qwen2.5:7b-instruct` via Ollama. Code revision: `issuer-profile-learning`.

## Runs

| Run | Configuration | normalized_accuracy | missing_rate | fabricated_rate |
| --- | --- | --- | --- | --- |
| 1 (baseline) | pre-detection, profile-guided extraction, veracity, fallback model all disabled | 0.9333 | 0.0 | 0.0143 |
| 2 | all new features enabled (defaults) | 0.9333 | 0.0 | 0.0143 |

## Comparison (run 2 vs baseline run 1)

`evaluate_extraction compare 1 2` — tolerance `APP_EVAL_REGRESSION_TOLERANCE=0.02`:

- Regressions: none. Every field's normalized accuracy is `same` (delta 0.0).
- Improvements: none.
- Per-entity: Cambridge English 0.9512, Oxford University Press 1.0,
  France Éducation international 0.8636 — identical across both runs.

Conclusion: enabling the issuer-profile learning path produces no
extraction regression on the golden set; parity is expected on this small
set since profile context is additive prompt information and pre-detection
only steers alias/profile selection on confident matches.
