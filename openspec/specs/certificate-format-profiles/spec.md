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
