# certificate-format-profiles Specification

## Purpose

Let the system recognize whether a document's layout and wording match the known certificate format of its claimed issuer, so text that merely resembles certificate data cannot pass as a genuine certificate, while legitimate year-to-year layout drift is tolerated.

## Requirements

### Requirement: Format profiles learned per issuer and issuance period
The system SHALL maintain format profiles for certifying entities, segmented by issuance year (cohort) and optionally by exam when enough approved samples exist, built exclusively from approved certificates.

#### Scenario: Approval contributes to the cohort profile
- **WHEN** a certificate is approved
- **THEN** its page text contributes format anchors to the profile of its entity and issuance-year cohort
- **AND** profiles for other cohorts are unaffected

#### Scenario: Insufficient samples keep the profile permissive
- **WHEN** a cohort has fewer approved certificates than the corroboration threshold
- **THEN** the profile contributes no negative evidence and only weakly positive evidence to the format score

#### Scenario: Rejected or unapproved documents never contribute
- **WHEN** a document is rejected or never approved
- **THEN** its text is never added to any format profile

### Requirement: Format anchors require corroboration
An anchor (a recurring textual marker such as a fixed label, boilerplate phrase, or code pattern) SHALL only be treated as expected for a cohort when it appears in at least two approved certificates of that cohort or in at least half of its samples, whichever is stricter.

#### Scenario: One-off wording does not define the format
- **WHEN** a literal string appears in only one approved certificate of a cohort
- **THEN** it is not treated as a required anchor for that cohort

#### Scenario: Stable boilerplate becomes an anchor
- **WHEN** a string appears across multiple approved certificates of the same cohort
- **THEN** it is treated as an expected anchor for that cohort

### Requirement: Format score per document
During classification, the system SHALL compute a format score between 0 and 1 expressing how well the document's text matches the profile of the entity it claims, preferring the cohort of the detected issuance year and falling back to entity-level matching when no cohort applies.

#### Scenario: Matching issuer format scores high
- **WHEN** a document classified to an entity contains most of that cohort's anchors and none of other entities' distinguishing anchors
- **THEN** its format score is high

#### Scenario: Plain text with certificate-like fields scores low
- **WHEN** a document contains plausible field values but lacks the issuer's expected anchors
- **THEN** its format score is low even if field extraction succeeded

#### Scenario: Year cohort disambiguates layout variants
- **WHEN** an entity changed its certificate layout between issuance years
- **THEN** a document is scored against the cohort matching its issuance year
- **AND** anchors exclusive to other years do not penalize it

#### Scenario: Unknown issuer has no format expectation
- **WHEN** a document's entity cannot be resolved
- **THEN** no format score is computed against any profile
- **AND** classification proceeds without format evidence

### Requirement: Format evidence influences confidence and review
The system SHALL store the computed format score on the certificate, blend it into the certificate's overall confidence, and SHALL emit a `format_mismatch` review reason when the score falls below the configured threshold while an entity was resolved.

#### Scenario: Format mismatch routes to review
- **WHEN** a certificate resolves to a known entity but its format score is below threshold
- **THEN** the certificate records a `format_mismatch` review reason
- **AND** it is routed to manual review

#### Scenario: Format score visible to reviewers
- **WHEN** a reviewer opens a certificate detail
- **THEN** the format score and, when available, the matched cohort are displayed alongside other confidence indicators

#### Scenario: Format evidence never approves by itself
- **WHEN** a document has a high format score
- **THEN** it does not bypass missing-field or low-extraction-confidence review reasons

### Requirement: Format score visible in the document list

The document list SHALL display each certificate's format score as a
visually distinct badge together with its cohort label when available,
and SHALL apply a warning visual treatment (color) to rows whose format
score is below the configured confidence threshold or whose format score
is absent while a profile exists for the entity. Documents without any
applicable profile SHALL be visually neutral, not flagged as errors.

#### Scenario: Low format score row is flagged

- **WHEN** a certificate's format score is below the confidence threshold
- **THEN** its row in the document list shows a warning-colored badge so
  it attracts reviewer attention

#### Scenario: No applicable profile is neutral

- **WHEN** a certificate's entity has no learned profile with enough
  samples
- **THEN** the format badge is absent or neutral and the row is not
  flagged

#### Scenario: Score and cohort shown

- **WHEN** a certificate has a computed format score
- **THEN** the list shows the score and the cohort label (entity, year,
  exam when segmented)

### Requirement: Filter documents by format confidence

The document list SHALL offer a filter that restricts results to
documents whose format score is below the confidence threshold
("doubtful format"), composing with the existing filters.

#### Scenario: Doubtful-format filter

- **WHEN** a reviewer selects the doubtful-format filter
- **THEN** only documents with a format score below the threshold (or an
  applicable profile that scored them low) are listed

### Requirement: Format profiles are manageable

Authorized reviewers SHALL be able to list format profiles (entity,
year, exam cohort, sample count, anchors), deactivate or reactivate a
profile, and trigger rescoring of documents affected by the change.
Deactivation SHALL exclude the profile from scoring without deleting it,
and the action SHALL be recorded for audit. Only reviewers or admins
SHALL manage profiles.

#### Scenario: Reviewer deactivates a wrong profile

- **WHEN** a reviewer deactivates a profile learned from bad data
- **THEN** subsequent format scoring ignores that profile, documents
  keep their stored scores until rescored, and the deactivation is
  recorded with actor and timestamp

#### Scenario: Viewer cannot manage profiles

- **WHEN** a viewer attempts to deactivate a profile
- **THEN** the request is rejected

#### Scenario: Rescore after reactivation

- **WHEN** a reviewer reactivates a profile and requests rescoring
- **THEN** affected certificates' format scores are recomputed against
  the current active profiles

### Requirement: Profiles guide extraction and validation

When an issuer is pre-detected with sufficient confidence, the system SHALL use that issuer's active profile to supply learned labels, value shapes, and expected anchors to extraction and to validate extracted label-value pairs. When no profile applies or detection is ambiguous, extraction SHALL use the global instruction and SHALL NOT apply issuer-specific negative evidence.

#### Scenario: Issuer profile guides extraction

- **WHEN** pre-detection resolves an issuer with an active profile
- **THEN** extraction uses that profile's labels, value shapes, and anchors
- **AND** extracted label-value pairs are checked against the profile

#### Scenario: Ambiguous detection falls back

- **WHEN** pre-detection cannot resolve an issuer with sufficient confidence
- **THEN** extraction uses the global instruction
- **AND** no issuer-specific anchor is treated as missing

#### Scenario: Profile never fabricates a value

- **WHEN** a profile expects a label but the document does not contain a value
- **THEN** the field stays empty and is not inferred from the profile

### Requirement: Profile quality and drift are measured

Each active profile SHALL track its sample count, precision and recall on approved samples, anchor churn, last rebuild time, and a drift signal when recent approved samples diverge from the profile. Low-quality or drifting profiles SHALL contribute less positive evidence and SHALL NOT contribute negative evidence until rebuilt.

#### Scenario: Drift is detected

- **WHEN** recent approved certificates from an issuer no longer contain anchors that older samples shared
- **THEN** the profile records a drift signal and is marked for rebuild
- **AND** documents are not penalized solely for the missing old anchors

#### Scenario: Low-quality profile is down-weighted

- **WHEN** a profile's measured precision falls below the configured quality floor
- **THEN** its positive contribution to format and veracity scores is reduced
- **AND** its anchors are not treated as required

### Requirement: Profiles carry a version and provenance

Each profile SHALL expose a version, the count and date range of samples it was built from, and the learning source. Extraction and review SHALL record and display the profile version used, so a result can be traced to the knowledge that produced it.

#### Scenario: Extraction records profile version

- **WHEN** extraction uses an issuer profile
- **THEN** the extraction run stores the profile version
- **AND** review can show which profile version was used

#### Scenario: Rebuild creates a new version

- **WHEN** a profile is rebuilt from new approved samples
- **THEN** it receives a new version and preserves the previous version for audit

### Requirement: Verified samples strengthen profiles

Approved certificates whose source was verified (`verified_at_source` or `manually_confirmed`) SHALL carry more weight than merely approved samples when building profiles. Rejected documents SHALL never contribute, and a verified sample SHALL NOT override a corroboration or conflict rule.

#### Scenario: Verified sample has higher weight

- **WHEN** a profile is built from a mix of approved and source-verified certificates
- **THEN** source-verified samples contribute more weight to anchors and value shapes

#### Scenario: Verification does not bypass corroboration

- **WHEN** only one verified sample contains a new anchor
- **THEN** the anchor is still not treated as expected until corroboration is met

### Requirement: Under-sampled year cohorts pool into entity profiles

When a (entity, year) cohort cannot reach the minimum sample count needed to
learn anchors, the system SHALL learn the profile from the entity-level pool
of approved certificates across multiple years instead of leaving the cohort
empty. Anchors SHALL still require corroboration across distinct documents,
so layout elements that appear in only one year SHALL NOT become anchors of
the pooled profile. Per-year drift detection SHALL keep working on the
samples that belong to each year.

#### Scenario: Single-year cohort falls back to the entity pool

- **WHEN** an entity has approved certificates spread across several years but
  fewer than the minimum in any single year
- **THEN** the profile is learned from the pooled samples
- **AND** only lines or layout features corroborated across distinct pooled
  documents become anchors

#### Scenario: Year-specific layout does not become a pooled anchor

- **WHEN** a boilerplate line or layout feature appears only in certificates
  from one year within the pool
- **THEN** it does not reach the corroboration threshold and is not stored as
  an anchor

#### Scenario: Drift is still detected per year

- **WHEN** recent approved samples from one year diverge from that year's
  established anchors
- **THEN** the drift signal is recorded for that cohort
- **AND** pooled anchors from other years are not treated as drift evidence

### Requirement: Anchors may include recurring layout features

In addition to text lines, the system MAY treat recurring structural layout
features — such as the presence and rough position of image regions (logos,
seals, photo areas) or repeated text blocks at stable positions — as anchor
candidates. Layout anchors SHALL obey the same corroboration threshold as
text anchors and SHALL be stored with enough information to be explained to
reviewers.

#### Scenario: Recurring logo region becomes a layout anchor

- **WHEN** approved certificates of a cohort consistently contain an image
  region in the same relative position
- **THEN** that layout feature is stored as an anchor with a human-readable
  description

#### Scenario: One-off image does not become an anchor

- **WHEN** only one approved certificate in the cohort contains a photo or
  image region
- **THEN** it does not reach corroboration and is not stored as an anchor

### Requirement: Layout anchors contribute to the format score

The format score SHALL count matched layout anchors alongside text anchors.
Missing layout anchors SHALL NOT count as negative evidence beyond the
profile's measured quality weight.

- **WHEN** a document is scored against a profile that has layout anchors
- **THEN** matching layout features contribute to the format score alongside
  text anchors
- **AND** missing layout anchors never count as negative evidence beyond the
  profile's measured quality weight

#### Scenario: Document matching layout anchors scores higher

- **WHEN** a document's layout features match the profile's layout anchors
- **THEN** its format score reflects the additional corroboration

### Requirement: Metadata-style lines are excluded from anchor candidacy

The system SHALL exclude lines that look like extracted metadata or key-value
noise (for example lowercase `key: value` pairs such as `language: english`)
from anchor candidates, so profiles learn certificate boilerplate rather than
pipeline artifacts.

#### Scenario: Metadata line is not learned

- **WHEN** a page text line matches a metadata pattern rather than printed
  certificate content
- **THEN** it is never stored as an anchor

#### Scenario: Printed labels still qualify

- **WHEN** a line is printed boilerplate such as "Date taken:" or a fixed
  certificate phrase
- **THEN** it remains eligible as an anchor candidate

### Requirement: Reviewers can preview the learned template anonymized

The format profiles screen SHALL let reviewers see a rendered sample
certificate for a profile, with the student name and other personal data
redacted, so they can verify the learned template visually. The preview SHALL
use an approved sample from the profile's cohort and SHALL NOT expose the
student's identity.

#### Scenario: Reviewer opens a profile preview

- **WHEN** a reviewer opens the sample preview of a format profile
- **THEN** the screen shows a rendered certificate page with personal data
  redacted
- **AND** the layout and boilerplate remain visible for comparison

#### Scenario: No sample available

- **WHEN** a profile has no approved sample that can be rendered
- **THEN** the preview shows a clear "no sample available" state
- **AND** no broken image or error is shown
