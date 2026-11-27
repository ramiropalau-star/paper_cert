# Spec Delta

## ADDED Requirements

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
