# Spec Delta

## ADDED Requirements

### Requirement: Approval feeds catalog learning
Approving or validating a certificate SHALL trigger catalog learning as part of the same operation, and the review history SHALL record that learning occurred.

#### Scenario: Approval records learning outcome
- **WHEN** a reviewer approves a certificate
- **THEN** catalog learning runs for that certificate
- **AND** the review history records which catalog entries, aliases, or rules were learned (or that none were needed)

#### Scenario: Learning failure does not block approval
- **WHEN** catalog learning encounters an error
- **THEN** the approval still completes
- **AND** the learning failure is recorded for follow-up

#### Scenario: Validation also teaches
- **WHEN** a reviewer validates a manually corrected certificate without approving it
- **THEN** catalog learning applies the same rules as for approval
