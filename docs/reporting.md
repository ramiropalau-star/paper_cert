# Excel reporting

Reports are generated asynchronously as `ReportJob` records. The UI creates a
job with filters; n8n triggers generation through the internal endpoint; the
app writes an `.xlsx` workbook into `APP_REPORT_OUTPUT_DIR` and the UI polls
the job status until it is `ready`, then offers the download.

## Creating a report

`/reports/` shows the job list and a filter form:

- **Alumno**: partial, case-insensitive match on the student name.
- **Idioma**: catalog language (id), code, name, or literal text.
- **Entidad**: catalog entity (id), name, or literal text.
- **Nivel**: matches CEFR level or literal level text.
- **Fecha de expedición**: exact date, or a `desde`/`hasta` range.
- **Incluir pendientes de revisión**: when checked, pending certificates are
  written to the secondary sheet.

Submitting the form stores the filters on the job and posts to the n8n
report webhook (`APP_N8N_REPORT_WEBHOOK_URL`) when configured. Without n8n
the job stays `queued` until the internal run endpoint is called.

## Job states

`queued` → `running` → `ready` | `error`

- `POST /internal/report-jobs/<id>/run/` (header `X-Internal-Token`) runs the
  job idempotently: a `ready` job returns its current state without
  regenerating.
- When no certificate matches the filters, the job ends in `error` with
  "No hay registros que coincidan con los filtros." and no file is produced.
- `GET /reports/<id>/status.json` returns the state for polling;
  `/reports/<id>/` auto-refreshes while the job is queued or running.
- `GET /reports/<id>/download/` streams the `.xlsx` (authenticated users only,
  only when `ready`).

## Workbook contents

Main sheet **Certificados** — approved records only, one row per certificate:

| Column | Source |
| --- | --- |
| Alumno | `student_name` |
| Idioma | catalog language name, else literal |
| Nivel | literal level text |
| Nivel MCER | normalized CEFR level |
| Equivalencia UV L2 | `equivalence` |
| Entidad certificadora | catalog entity name, else literal |
| Fecha de expedición | Excel date cell |
| Certificado o examen | catalog exam name, else literal |
| Puntuación | literal score |
| Estado | `Aprobado` |
| Fecha de procesamiento | document `updated_at` as date |
| Referencia al documento | Paperless document id (or local pk) |
| Nombre del fichero | document `original_filename` |
| Código de certificado | `certificate_code` |
| Centro de examen | `test_center_literal` |
| Organismo emisor | `issuing_body_literal` |
| Motivo del rechazo | reason of the latest `reject` review event (empty for non-rejected) |

The header row is always present, and every sheet has an auto-filter
over all columns. Date cells use Excel date formatting so they sort and
filter correctly. Manually corrected values are reflected because the report
reads the current certificate rows.

## Pending sheet

When `include_pending` is set, a second sheet named **Pendientes de revisión**
is added with the same columns; its `Estado` column reads
`Pendiente de revisión`, so unreviewed records are never presented as
confirmed data.

## Rejected sheet

When at least one certificate matches the filters with status `rejected`, a
third sheet named **Rechazados** is added with the same columns; its `Estado`
column reads `Rechazado` and `Motivo del rechazo` carries the reason entered
when the certificate was rejected. Rejected records never appear in the main
or pending sheets.

A generated sample workbook is committed at
[`docs/examples/report-sample.xlsx`](examples/report-sample.xlsx).

## Columns

The workbook includes "Equivalencia UV L2" (the accredited level resolved
from the UV equivalence table or entered manually during review) next to
"Nivel MCER". The "Pendientes de revisión" sheet lists both `pending` and
`validated` certificates with their individual status labels.
