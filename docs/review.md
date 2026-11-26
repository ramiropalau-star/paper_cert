# Review workflow and audit

Every extracted certificate enters `pending_review`. A reviewer verifies the
data against the original, corrects it if needed, and approves or rejects it.
Only approved records enter the main Excel report.

## Queue and filters

`/documents/` lists all documents with pagination (25 per page) and filters:

- **Estado**: procesados, pendientes de revisión, aprobados, rechazados, error.
- **Buscar**: student name or original filename (partial, case-insensitive).
- **Idioma / Entidad**: catalog entry or literal text.
- **Nivel**: CEFR level or literal level text.
- **Fecha de expedición**: exact date (`YYYY-MM-DD`).
- **Catálogo**: "Pendiente de catálogo" lists only documents with at least
  one unresolved catalog literal (entity, exam, or language).
- **Verificación**: "Con campos sin verificar" lists only certificates with
  fields marked unverified (see below).

The table itself supports client-side review aids on top of the server
filters: a per-column filter row under the header, click-to-sort on every
column header (ascending/descending), and pagination defaulting to 10 rows
with a page-size selector (10/25/50/100/all, remembered per session). Each
row with a Paperless original has an eye button that opens the document in a
lightbox for quick visual review without leaving the list. The "Equiv. UV"
column links to the matching equivalence rule on `/catalog/equivalences/`.

The list also shows the student **NPA**, parsed from the original filename
(`<año>ERASMUS<NPA>_...`, e.g. `2027ERASMUSWF29402_I....pdf` → `WF29402`);
files without that pattern show `—`.

Filters combine with AND semantics. The same filters (plus an
**Organismo emisor** text filter) are available in the gallery.

## Processing queue

`/documents/queue/` is a live view of documents currently moving through the
pipeline (`received` → `stored` → `text_ready` → `extracted` →
`classified`). It refreshes automatically and is useful to confirm intake is
flowing while uploads or a Paperless sync are in progress.

## Gallery and bulk review

`/documents/gallery/` shows certificate documents as a visual grid: each card
renders the original image (or a placeholder for PDFs), the student name,
language, certifying entity, level, and UV L2 equivalence. Clicking a card
opens the review detail page.

Reviewers can tick several cards and apply a bulk action — **Validar** or
**Aprobar** — via `POST /documents/bulk-review/`. Each document goes through
the same `validate_certificate`/`approve_certificate` services as the
single-record buttons, so required-field checks and audit events apply per
record; failures are reported per file in the flash messages. The bulk action
preserves the active gallery filters on redirect.

## Detail view

`/documents/<id>/` shows the document metadata (filename, processing state,
text method `embedded`/`ocr`/`mixed`, page count, fingerprint), a link to the
original in Paperless-ngx, the extracted fields with per-field evidence
quotes, review warnings mapped from review reasons, and the review actions.

The detail page offers **Anterior/Siguiente** buttons that walk the
pending-review queue (ordered by upload date), plus a link back to the
filtered pending list.

Field warnings:

| Reason | Warning |
| --- | --- |
| `unknown_language` | Idioma no identificado |
| `unknown_entity` | Entidad pendiente de identificar |
| `ambiguous_date` | Fecha ambigua o sin categoría |
| `low_confidence` | Confianza baja |
| `missing_essential_fields` | Faltan campos obligatorios |
| `multiple_certificates` | Posibles múltiples certificados |
| `non_certificate` | No parece un certificado de idioma |
| `equivalence_not_found` | Sin equivalencia UV L2 para el examen |
| `format_mismatch` | El formato no coincide con el perfil conocido del emisor |

Pipeline-stage codes (`ocr_failed`, `insufficient_text`,
`low_ocr_confidence`, `original_unavailable`, `model_unavailable`, …) are
also translated into operator-readable labels; see
`documents/review_display.py` for the full mapping.

## Catalog resolution

When a certificate's `entity`, `exam`, or `language` literal did not match
the catalog, the record shows a **Catálogo pendiente** badge in the list,
gallery, and detail page, and the unresolved value offers a **Resolver**
action (reviewers and admins only; viewers see the badge read-only).

`/catalog/resolve/?document=<id>&field=<entity|exam|language>` lets the
reviewer either pick an existing catalog entry (searchable by name or
alias) or create a new one prefilled with the printed literal. Exam
resolution is scoped to the certificate's resolved entity — if the entity
is also unresolved, the page links to resolving it first. Languages can
only be matched to existing entries plus a new alias.

A successful resolution:

- assigns the catalog foreign key and freezes the field in
  `manual_fields` so reprocessing keeps the human choice;
- registers the printed literal as an alias (`EntityAlias`, `ExamAlias`,
  or `LanguageAlias`) — idempotent, and never reassigns an alias already
  owned by another entry (the conflict is reported instead);
- writes an `edit` `ReviewEvent` with the actor and before/after ids;
- optionally re-runs classification (on by default) so dependent fields
  and review reasons refresh — e.g. `unknown_entity` clears once the
  entity resolves.

## Manual editing

Reviewers (and admins) edit directly on the detail page: the extracted-data
table shows an **Editar** button that swaps every value cell for the
corresponding input (catalog selects for language/entity/exam plus literal
text fields, dates, CEFR level, equivalence) without duplicating the values
in a second form. **Guardar cambios** submits to the same edit endpoint;
**Cancelar** returns to the read view. Viewers always see the read-only
table.

Editable fields: literals, catalog
selections (language, entity, exam), CEFR level, all four dates, and the
certificate code. Dates are validated as `YYYY-MM-DD`. Manual CEFR edits set
`cefr_source = manual`.

Each change writes a `ReviewEvent` of type `edit` capturing the actor,
timestamp, and before/after values for every changed field.

### Manual-field freeze

Every field edited during review is recorded in
`certificate.manual_fields`. Frozen fields are preserved verbatim on
reprocess/re-extraction instead of being overwritten by the pipeline, so a
human correction is never silently lost. The detail page offers a
**Liberar campo** action per field (`POST /documents/<id>/release-field/`)
that removes it from `manual_fields` so the next reprocess can overwrite it
again.

## Approve and reject

- **Approve** requires `viewer`-less roles (`reviewer`/`admin`) and all
  required fields: student name, resolved language, resolved entity, level
  or score, and issue date. Missing fields block approval and are listed in
  the error message. Approval sets `review_status = approved`, moves the
  document to `approved`, records an `approve` event, and removes the
  `Otros` Paperless label.
- **Reject** requires a non-empty reason. It sets `review_status =
  rejected`, moves the document to `rejected`, and records a `reject` event
  with the reason.

Viewers can read everything but cannot edit, approve, reject, or reprocess
(HTTP 403).

## Reprocess

Reprocessing resets the document to `stored` (pages are kept; the pipeline
re-runs text acquisition, extraction, and classification), returns the
certificate to `pending`, clears the error reason, records a `reprocess`
event, and notifies the n8n processing webhook when
`APP_N8N_PROCESSING_WEBHOOK_URL` is configured. No duplicate document or
certificate rows are created; previous values remain in the event history.

**Re-extract** (`Re-extraer` button, reviewers) is the direct alternative for
re-running only extraction + classification against the stored page texts,
without the n8n webhook round-trip. It resets the document to `text_ready`,
runs the extraction service synchronously (expect ~20-60 s for the model
call), then classification, preserves `manual_fields`, and records a
`reextract` event. Use it to rescue documents stuck mid-pipeline or to
re-apply a newer prompt/fallback logic to a single certificate.

## Unverified fields

Extraction verifies every literal field's evidence quote against the cited
page. When a quote cannot be verified, the value is **kept but flagged** in
`certificate.unverified_fields` instead of failing the whole extraction —
the same trust model as any other extracted value, but badged "sin verificar"
in the detail view and marked `?` in the list. Deterministic fallbacks
(student name, score, issue date) and values adopted by the focused second
pass are flagged the same way. Editing a field or marking the certificate
**validated** clears its unverified marks; approving does not require them
to be resolved first.

## History

`/documents/<id>/history/` lists every `ReviewEvent` (edit, validate,
approve, reject, reprocess, reextract, learn) in chronological order with actor,
timestamp, reason, and the before/after payloads. Approve/validate events
carry the learning outcome; `learn` events are emitted by the
`learn_from_history` backfill.

## Validated state

Reviewers can mark a pending certificate as `validated` ("Validado") via
`POST /documents/<id>/validate/`. Validation records a `validate` audit
event and signals that a human checked the extracted values, but the
document stays in `pending_review` and out of the approved report sheet
until it is approved. Validated records appear in the report's
"Pendientes de revisión" sheet with status "Validado".

## In-app document viewer

`GET /documents/<id>/original/` streams the original file from Paperless
through Django (authenticated, viewer role or above) with the detected
content type, so reviewers can inspect the document inside the review page
without logging into Paperless. The detail page embeds it in an iframe.

## Learning from review

Approving or validating a certificate teaches the system (post-commit, never
blocking the decision):

- Printed literals that resolved to catalog entries are saved as aliases, so
  the next document with the same wording classifies automatically.
- A manually assigned entity/exam on an unknown literal creates the missing
  `Exam` entry (entities can also be created inline via catalog resolution).
- A manually corrected UV L2 equivalence creates an unbanded `Equivalence`
  rule (`source="review"`) when none exists for that exam/level.
- A manually corrected CEFR level creates an **inactive**
  `CefrConversionRule` candidate pinned to the observed score; a human must
  widen the band and activate it.
- Conflicting aliases are never overwritten; they are recorded in the
  learning outcome attached to the approve/validate `ReviewEvent`.

`python manage.py learn_from_history [--dry-run]` replays the same learning
over already-approved/validated certificates (idempotent).

## Format profiles

Each entity accumulates a textual format profile per issuance year, built
from approved certificates' page text. Classification scores every document
against the profile of its claimed entity/year cohort and blends the score
into `certificate.confidence` (30% weight). A `format_mismatch` review
reason is emitted when the score falls below `APP_FORMAT_SCORE_THRESHOLD`
(default 0.4). Anchors require corroboration across at least two approved
samples (`APP_FORMAT_MIN_SAMPLES`) or half the cohort, whichever is
stricter, so single-document quirks never define a format. See
`catalog.FormatProfile` and `documents/services/format_profile.py`.
