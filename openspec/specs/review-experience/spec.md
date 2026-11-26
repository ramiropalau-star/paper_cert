# review-experience Specification

## Purpose
Defines how the document review screen communicates reasons, confidence, warnings, status, and actions so a reviewer can decide without translating internal codes.

## Requirements

### Requirement: Review reasons use human labels and explanations

The review screen SHALL present each known review reason with a human label and a short explanation of what the reviewer should check. The raw reason code SHALL NOT be the primary visible text.

#### Scenario: Known reason is explained
- **WHEN** a certificate has the `low_confidence` reason
- **THEN** the screen shows a readable label and an explanation
- **AND** it does not show the raw code as the main text

#### Scenario: Multiple reasons are readable
- **WHEN** a certificate has several review reasons
- **THEN** each reason is shown once with its label and explanation
- **AND** duplicate codes are not repeated

### Requirement: Unknown reasons degrade without leaking codes

The review screen SHALL show a generic review message for a reason code it does not recognize. It MAY expose the raw code in a secondary detail for diagnostics, but the primary text SHALL remain understandable.

#### Scenario: Unknown reason is generic
- **WHEN** a review reason has no mapping
- **THEN** the screen shows a generic "requires manual review" message
- **AND** the raw code is not the primary text

### Requirement: Confidence is shown as a percentage with a quality label

The review screen SHALL display extraction confidence as a percentage and a high, medium, or low label. The raw decimal MAY remain available in a secondary detail, but it SHALL NOT be the only representation.

#### Scenario: Confidence is readable
- **WHEN** a certificate has confidence `0.87`
- **THEN** the screen shows `87%` and a quality label
- **AND** the raw decimal is not the primary value

#### Scenario: Missing confidence is explicit
- **WHEN** a certificate has no confidence value
- **THEN** the screen shows a clear "not available" state
- **AND** it does not show `0%` as if it were measured

### Requirement: Warnings point to the field they affect

The review screen SHALL associate each mapped warning with the field it concerns and SHALL provide an explicit "no observations" state when there are no review reasons.

#### Scenario: Warning points to its field
- **WHEN** the `unknown_language` reason is present
- **THEN** the warning is shown next to the language field or links to it
- **AND** the reviewer can find the affected field without guessing

#### Scenario: No observations are explicit
- **WHEN** a certificate has no review reasons
- **THEN** the screen shows a clear no-observations message
- **AND** it does not render an empty list

### Requirement: Destructive review actions require explicit confirmation

The review screen SHALL require an explicit confirmation before reprocessing a document. It SHALL keep the rejection reason required. A request without the confirmation SHALL NOT reprocess the document and SHALL show a clear message.

#### Scenario: Reprocess requires confirmation
- **WHEN** a reviewer submits the reprocess action without confirming
- **THEN** the document is not reprocessed
- **AND** the screen explains that confirmation is required

#### Scenario: Confirmed reprocess proceeds
- **WHEN** a reviewer confirms the reprocess action
- **THEN** the document is reprocessed through the existing pipeline

### Requirement: Status and actions are accessible and unambiguous

Every review status badge SHALL include text, not color alone. Every review action SHALL have an accessible name that states its effect, and the review screen SHALL remain operable by keyboard.

#### Scenario: Status is not color-only
- **WHEN** a document is shown as approved, rejected, pending, or in error
- **THEN** the status text is present in the badge
- **AND** the meaning does not depend on color alone

#### Scenario: Actions are keyboard operable
- **WHEN** a reviewer navigates the review actions with the keyboard
- **THEN** each action is reachable and has a visible focus state
- **AND** each action's accessible name states what it does
