# Spec Delta

## ADDED Requirements

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
