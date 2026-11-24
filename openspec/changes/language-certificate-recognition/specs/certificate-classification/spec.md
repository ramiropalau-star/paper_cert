# Spec Delta

## Purpose

Map literal certificate data to a maintained catalog of languages, certifying entities, and exams without losing the document's original wording, and apply only explicit or formally approved normalization rules.

## ADDED Requirements

### Requirement: Editable catalog without code changes
The system SHALL maintain an editable catalog of languages, certifying entities, exams, and aliases that authorized users can extend, and SHALL resolve classification from catalog data rather than hardcoded lists.

#### Scenario: New entity added
- **WHEN** an authorized user adds a certifying entity with one or more aliases
- **THEN** subsequent certificates referencing any of those aliases resolve to that entity
- **AND** no application code change or redeployment is required

#### Scenario: New language added
- **WHEN** an authorized user adds a language with its entities and exams
- **THEN** certificates in that language can be classified against the new catalog entries

### Requirement: Preserve literal and normalized entity values
The system SHALL store both the entity text exactly as printed in the document and the normalized catalog entity, and SHALL NOT replace the literal value with the normalized one.

#### Scenario: Alias resolved to canonical entity
- **WHEN** a document prints an alias or variant of a cataloged entity
- **THEN** the system stores the printed text as the literal entity
- **AND** stores the catalog entity as the normalized entity

#### Scenario: Original wording remains available
- **WHEN** a reviewer inspects a classified certificate
- **THEN** the literal entity text is visible alongside the normalized entity

### Requirement: Distinguish certifying entity roles
The system SHALL distinguish the examining entity, the issuing body, and the test center when the document provides enough information to tell them apart, and SHALL NOT assign a role that the document does not support.

#### Scenario: Roles differ and are recorded separately
- **WHEN** a certificate identifies different organizations as examining entity, issuing body, or test center
- **THEN** each role is stored in its own field

#### Scenario: Single organization not multiplied
- **WHEN** the document names only one organization and does not clarify its role
- **THEN** the system does not invent additional roles
- **AND** the ambiguity is available for review

### Requirement: Unknown entities remain pending identification
The system SHALL keep an unrecognized entity as printed and SHALL mark it as "Entidad pendiente de identificar" without assigning it to a similar catalog entity.

#### Scenario: Unknown entity preserved literally
- **WHEN** the printed entity does not match any catalog entity or alias
- **THEN** the literal text is stored unchanged
- **AND** the record is marked "Entidad pendiente de identificar"
- **AND** the record is routed to review

#### Scenario: No automatic fuzzy assignment
- **WHEN** a printed entity is similar but not identical to a catalog alias
- **THEN** the system does not automatically classify it as that entity
- **AND** the decision is left to a reviewer

### Requirement: Normalize the certified language
The system SHALL normalize the certified language using the catalog and SHALL route certificates whose language cannot be determined to review.

#### Scenario: Language variant normalized
- **WHEN** a certificate identifies a language through any cataloged name or alias
- **THEN** the system stores the normalized catalog language for that certificate

#### Scenario: Undetermined language
- **WHEN** the certified language cannot be determined from the document
- **THEN** the language remains unset
- **AND** the record is routed to review

### Requirement: Assign CEFR level only from explicit or approved rules
The system SHALL assign a normalized CEFR level only when the document states it explicitly or when a documented, approved conversion rule exists for that exam.

#### Scenario: Explicit CEFR level
- **WHEN** the document explicitly states a CEFR level
- **THEN** the system stores that CEFR level in the normalized field

#### Scenario: Approved conversion rule applied
- **WHEN** the document does not state a CEFR level but an approved conversion rule exists for that exam and score range
- **THEN** the system assigns the CEFR level produced by that rule
- **AND** records that the level was derived from the approved rule

#### Scenario: No conversion without approved rule
- **WHEN** no explicit CEFR level and no approved conversion rule apply
- **THEN** the CEFR field remains empty
- **AND** the literal level or score is preserved unchanged

### Requirement: Normalize and distinguish certificate dates
The system SHALL store dates in YYYY-MM-DD format, SHALL retain the original detected date text when useful for review, and SHALL keep issue date, exam date, and result date as separate fields.

#### Scenario: Issue date normalized
- **WHEN** the document states an issue date
- **THEN** the system stores it in YYYY-MM-DD format in the issue-date field
- **AND** retains the original date wording when it helps review

#### Scenario: Distinct exam and result dates
- **WHEN** the document states an exam date and a result date that differ from the issue date
- **THEN** each date is stored in its corresponding field

#### Scenario: Single undetermined date
- **WHEN** only one date appears and its category cannot be determined
- **THEN** the system stores it as a detected date without assigning issue, exam, or result meaning

### Requirement: Seed catalog covers common certifying entities
The delivered seed catalog SHALL include the specified English, French, German, Spanish, Italian, and Portuguese entities and exams, and SHALL support entities and exams for any other language through catalog data.

#### Scenario: English entities seeded
- **WHEN** the catalog is initialized
- **THEN** it includes ETS (TOEFL), Cambridge English, IELTS, Pearson (PTE), LanguageCert, Duolingo English Test, TOEIC, Trinity College London, and OET with their common aliases

#### Scenario: French, German, Spanish, Italian, and Portuguese entities seeded
- **WHEN** the catalog is initialized
- **THEN** it includes France Éducation international (DELF, DALF, TCF), CCI Paris Île-de-France (TEF), Goethe-Institut, telc, TestDaF, ÖSD, DSH, DTZ/g.a.s.t., Instituto Cervantes (DELE), SIELE, CELU, CILS, CELI, PLIDA, Cert.IT, CAPLE, and CELPE-Bras

#### Scenario: Additional languages supported
- **WHEN** an authorized user adds entities or exams for Japanese, Chinese, Korean, Dutch, Russian, Swedish, or another language
- **THEN** the catalog accepts and classifies them without code changes
