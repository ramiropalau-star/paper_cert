# Spec Delta

## ADDED Requirements

### Requirement: Catalog-pending badge on unresolved literals

The document list, gallery, and review detail SHALL mark records whose
`entity`, `exam`, or `language` literal failed catalog resolution with a
visible "catálogo pendiente" indicator, distinct from generic review
warnings. Resolved records SHALL NOT show the badge.

#### Scenario: Unresolved entity shows badge
- **WHEN** a certificate has `entity = NULL` and an `entity_literal`
- **THEN** the list row, gallery card, and detail page show the
  catalog-pending indicator

#### Scenario: Resolved entity hides badge
- **WHEN** the certificate's entity literal resolved to a catalog `Entity`
- **THEN** no catalog-pending indicator is shown for that field

### Requirement: Unresolved-catalog filter

The document queue SHALL offer a filter that lists only documents with at
least one unresolved catalog reference (`entity`, `exam`, or `language`
literal without a matching foreign key), combinable with existing filters.

#### Scenario: Filter pending catalog work
- **WHEN** a reviewer applies the unresolved-catalog filter
- **THEN** only documents with at least one unresolved catalog literal are
  listed
- **AND** the filter combines with state/search/other filters using AND
  semantics
