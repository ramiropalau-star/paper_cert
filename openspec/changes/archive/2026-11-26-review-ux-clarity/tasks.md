# Tasks

## 1. Review presentation helpers

- [x] 1.1 Add `documents/review_display.py` with reason labels/explanations, the unknown fallback, de-duplication, and confidence percentage/band helpers; verify known, unknown, duplicate, `None`, and boundary values with unit tests.
- [x] 1.2 Pass the new context values from `review_detail` without removing the existing `warnings` mapping; verify the view context with tests.

## 2. Readable reasons, warnings, and confidence

- [x] 2.1 Replace the raw reason list in `detail.html` with labelled items, explanations, field links, the no-observations state, and a secondary raw-code detail; verify the rendered output contains labels and does not show a raw code as primary text.
- [x] 2.2 Render confidence as a percentage with a quality badge and a secondary raw value; verify missing confidence shows "No disponible" and does not render `0%`.
- [x] 2.3 Keep inline field warnings and link them to the affected field; verify the warning remains readable and the link resolves to the fields table.

## 3. Confirmation for destructive reprocessing

- [x] 3.1 Create the shared reprocess form include with a required confirmation checkbox and use it in every reprocess form on the review screen; verify the checkbox is present in each form.
- [x] 3.2 Validate `confirm_reprocess` in `review_reprocess` and reject a request without it without calling the reprocess service; verify the blocked and confirmed paths with view tests.

## 4. Accessibility and styles

- [x] 4.1 Add accessible names to review actions, ensure status badges contain text, and add visible focus styles for buttons and links; verify with template tests and a keyboard smoke check.
- [x] 4.2 Add styles for reason items, confidence bands, the confirmation control, and focus states; verify the review screen renders at desktop and narrow widths without overlapping controls.

## 5. Integration verification

- [x] 5.1 Run the review view and template tests plus the full suite; record the observed results.
- [x] 5.2 Run `openspec validate review-ux-clarity --strict` and fix any artifact issues.

## Workflow follow-up

- Archive the change after the project's review requirements are satisfied.
- Verify the archived `review-experience` spec and the resulting capability baseline.
