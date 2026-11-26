# Design

## Context

`review_detail` already maps reason codes to per-field warning messages through `FIELD_WARNINGS`, but the template also renders the raw `certificate.review_reasons` list. Confidence is rendered with `floatformat:2`. The reprocess action is a plain POST form with no confirmation, and it can discard manual edits. Status badges already contain text; color is defined in CSS.

## Goals / Non-Goals

**Goals:**

- Replace raw reason codes with labels and explanations.
- Show confidence as a percentage with a quality band.
- Link warnings to the affected field.
- Require explicit confirmation before reprocessing.
- Keep the screen accessible by keyboard and not color-dependent.

**Non-Goals:**

- Changing review state transitions, approval rules, or the extraction model.
- Redesigning the full review layout or navigation.
- Adding client-side frameworks or a modal library.

## Decisions

### 1. Centralize reason presentation in a helper

Add `documents/review_display.py` with:

- `REVIEW_REASON_DETAILS`: code → `(label, explanation)` for the known codes (`unknown_language`, `unknown_entity`, `ambiguous_date`, `low_confidence`, `missing_essential_fields`, `multiple_certificates`, `non_certificate`);
- `UNKNOWN_REASON = ("Revisión adicional", "El documento necesita una revisión manual adicional.")`;
- `review_reason_items(reasons)` returning a de-duplicated list of dicts with `code`, `label`, `explanation`, and `known`;
- `confidence_display(value)` returning `None` or a dict with `percent` (integer), `raw` (two-decimal string), and `band` (`high` ≥ 0.85, `medium` ≥ 0.60, otherwise `low`).

The view passes `review_reason_items` and `confidence_display`. The existing `warnings` mapping stays for inline field warnings. Raw codes appear only inside a `<details>` element for diagnostics.

Alternatives: put labels in the template (hard to test, duplicates logic), change the model choices (codes are stored data; presentation belongs in the view). Rejected.

### 2. Render reasons as a labelled list with field links

Replace the raw `<ul>` with a list of items showing the label, the explanation, and a link to `#datos` (the fields table). When the list is empty, show "Sin observaciones". For unknown codes, show the generic label and put the code in a `<details><summary>Ver código</summary>` block.

### 3. Render confidence as a percentage with a band

Replace the decimal-only cell with `{{ confidence.percent }}%`, a badge using `confidence.band`, and the raw decimal in a secondary `<details>`. If `confidence` is `None`, show "No disponible" without a percentage.

### 4. Require a server-validated confirmation for reprocessing

Create `documents/templates/documents/_reprocess_form.html` containing the CSRF token, a required checkbox labelled with the consequence ("Confirmo que quiero reprocesar y descartar los cambios manuales"), and the submit button. Include it in all reprocess forms. `review_reprocess` checks `request.POST.get("confirm_reprocess") == "on"`; if absent, it adds an error message and redirects without calling `reprocess_document`. The checkbox's `required` attribute is a convenience; the server check is authoritative.

Alternatives: JavaScript `confirm()` (not reliable, CSP concerns), no confirmation (current problem). Rejected.

### 5. Improve accessibility without a redesign

Add `aria-label` to each review action describing its effect, keep the status text inside the badge, add `:focus-visible` outlines for buttons and links, and associate the reason list with the fields table through the link. The confirmation checkbox has a real `<label>`, and the reason details use native `<details>`.

## Risks / Trade-offs

- More visible text can lengthen the screen → keep explanations short and place raw codes in details.
- The confidence bands are presentation thresholds, not model decisions → document them and keep the raw value available.
- The confirmation adds a step for a legitimate action → it prevents silent loss of manual edits; the checkbox is one click.
- Unknown reason codes may appear after a future extractor change → the generic fallback keeps the screen usable.

## Migration Plan

No database migration. Deploy the template, helper, view check, and CSS together. Rollback restores the previous template and view; stored data is unchanged.

## Open Questions

None that change the spec, approach, or task breakdown.
