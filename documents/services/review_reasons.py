"""Shared review-reason merging for pipeline stages.

Each stage owns a set of reason codes it is responsible for refreshing. The
merge keeps every reason the stage does not own (in order), appends the stage's
fresh reasons that are not already present, and dedupes the result.
"""


def merge_review_reasons(existing, fresh, owned_codes) -> list[str]:
    """Merge ``fresh`` reasons into ``existing`` for a stage owning ``owned_codes``.

    Reasons in ``existing`` that belong to ``owned_codes`` are dropped (the
    stage recomputes them); all other reasons are preserved in order. Fresh
    reasons already present are not duplicated.
    """
    kept = [reason for reason in (existing or []) if reason not in owned_codes]
    merged = kept + [reason for reason in fresh if reason not in kept]
    return list(dict.fromkeys(merged))
