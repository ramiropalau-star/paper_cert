# Proposal

## Why

The review screen exposes internal reason codes such as `unknown_language` or `low_confidence`, shows confidence as a decimal, and presents several destructive or final actions with little context. Reviewers must translate codes mentally and can trigger a reprocess that discards edits without an explicit confirmation. The result is slower decisions and avoidable mistakes.

## What Changes

- **Readable review reasons**: map every known reason code to a human label and a short explanation; show unknown codes with a generic message and keep the raw code in a secondary detail, not as the primary text.
- **Readable confidence**: display extraction confidence as a percentage with a high/medium/low label, and keep the numeric value available in a secondary detail.
- **Safer actions**: require an explicit confirmation for reprocessing, keep the rejection reason required, and give each action an accessible label and a clear consequence.
- **Actionable warnings**: link each mapped warning to the field it affects, and show a clear "no observations" state when there are no reasons.
- **Accessible status**: pair every status badge with text; do not rely on color alone.
- **Tests and styles**: cover reason mapping, unknown fallback, confidence formatting, confirmation, and accessible labels.

## Capabilities

### New Capabilities

- `review-experience`: durable behavior for presenting review reasons, confidence, warnings, status, and review actions clearly and safely.

### Modified Capabilities

None.

## Impact

- **Templates**: `documents/templates/documents/detail.html`.
- **Views and helpers**: `documents/views.py`, a reason-label mapping, and a confidence formatting helper.
- **Styles**: review-specific CSS for badges, warnings, and the confirmation control.
- **Reviews**: `review_reprocess` validates the confirmation field.
- **Risk**: changing the review template can affect the reviewer workflow; tests cover the rendered labels and confirmation behavior, and no data model changes are required.
