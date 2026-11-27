"""Review UI: veracity badge/breakdown, inline thumbnail, high-score safety."""

import pytest
from django.contrib.auth.models import Group, User
from django.urls import reverse

from documents.models import Certificate
from documents.review_display import (
    veracity_band,
    veracity_breakdown_items,
    veracity_display,
)
from documents.tests.factories import (
    add_page,
    make_certificate,
    make_document,
)

pytestmark = pytest.mark.django_db


def make_user(username: str, roles: tuple[str, ...] = ()) -> User:
    user = User.objects.create_user(username, password="password")
    for role in roles:
        group, _ = Group.objects.get_or_create(name=role)
        user.groups.add(group)
    return user


# --- display helpers ---


def test_veracity_display_bands():
    assert veracity_display(0.9)["band"] == "high"
    assert veracity_display(0.6)["band"] == "medium"
    assert veracity_display(0.2)["band"] == "low"
    assert veracity_display(None) is None
    assert veracity_band("not-a-number") is None


def test_veracity_breakdown_labels_and_fallback():
    items = veracity_breakdown_items(
        {
            "components": {
                "source": {"value": 1.0, "weight": 0.4, "label": "Verificación en origen"},
                "mystery": {"value": 0.1},
            }
        }
    )
    assert items[0]["label"] == "Verificación en origen"
    fallback = next(i for i in items if i["name"] == "mystery")
    assert fallback["label"] == "Componente de veracidad"
    assert fallback["weakest"] is True
    assert items[0]["weakest"] is False


# --- document list ---


def test_list_shows_veracity_value_and_band(client):
    viewer = make_user("lu", ("viewer",))
    document = make_document(paperless_document_id="55")
    add_page(document, text="page")
    make_certificate(
        document=document,
        veracity_score=0.9,
        veracity_components={
            "weights_version": "veracity-v1",
            "components": {"source": {"value": 1.0, "weight": 0.4, "label": "Verificación"}},
        },
        format_score=0.8,
    )
    client.force_login(viewer)
    response = client.get(reverse("documents:list"))
    content = response.content.decode()

    assert "Veracidad 90%" in content
    assert "row-veracity-high" in content
    # Format score remains a separate badge.
    assert "Formato" in content
    # Lazy inline thumbnail linking to the review detail.
    assert 'class="doc-thumb"' in content
    assert 'loading="lazy"' in content
    assert f'href="/documents/{document.pk}/"' in content
    # Separate zoom control still present.
    assert "preview-btn" in content


def test_list_missing_veracity_is_explicit(client):
    viewer = make_user("ln", ("viewer",))
    document = make_document()
    add_page(document, text="page")
    make_certificate(document=document, veracity_score=None)
    client.force_login(viewer)
    response = client.get(reverse("documents:list"))
    content = response.content.decode()
    assert "Veracidad no disponible" in content
    assert "Veracidad 0%" not in content


def test_list_row_without_original_shows_placeholder(client):
    viewer = make_user("lp", ("viewer",))
    document = make_document()  # no paperless_document_id
    add_page(document, text="page")
    make_certificate(document=document)
    client.force_login(viewer)
    response = client.get(reverse("documents:list"))
    content = response.content.decode()
    assert "thumb-placeholder" in content
    assert 'class="doc-thumb"' not in content


# --- review detail ---


def test_detail_shows_veracity_breakdown(client):
    viewer = make_user("ld", ("viewer",))
    document = make_document(paperless_document_id="77")
    add_page(document, text="certificate text")
    make_certificate(
        document=document,
        veracity_score=0.62,
        veracity_components={
            "weights_version": "veracity-v1",
            "components": {
                "source": {"value": 0.4, "weight": 0.4, "label": "Verificación en origen"},
                "format": {"value": 0.9, "weight": 0.25, "label": "Coincidencia de formato"},
            },
        },
        veracity_weights_version="veracity-v1",
    )
    client.force_login(viewer)
    response = client.get(reverse("documents:detail", args=[document.pk]))
    content = response.content.decode()

    assert "Veracidad 62%" in content
    assert "Media" in content
    assert "Verificación en origen" in content
    assert "Coincidencia de formato" in content
    assert "componente más débil" in content
    assert "veracity-v1" in content


def test_detail_missing_veracity_is_explicit(client):
    viewer = make_user("ldn", ("viewer",))
    document = make_document()
    add_page(document, text="certificate text")
    make_certificate(document=document, veracity_score=None)
    client.force_login(viewer)
    response = client.get(reverse("documents:detail", args=[document.pk]))
    content = response.content.decode()
    assert "Veracidad no disponible" in content


def test_detail_renders_source_document_by_default(client):
    viewer = make_user("lr", ("viewer",))
    document = make_document(paperless_document_id="88")
    add_page(document, text="certificate text")
    make_certificate(document=document)
    client.force_login(viewer)
    response = client.get(reverse("documents:detail", args=[document.pk]))
    content = response.content.decode()
    assert "review-doc" in content
    assert f'src="/documents/{document.pk}/original/"' in content


def test_high_veracity_keeps_reasons_and_approval(client):
    reviewer = make_user("lh", ("reviewer",))
    document = make_document()
    add_page(document, text="certificate text")
    make_certificate(
        document=document,
        veracity_score=0.95,
        review_status=Certificate.ReviewStatus.PENDING,
        review_reasons=["low_confidence"],
    )
    client.force_login(reviewer)
    response = client.get(reverse("documents:detail", args=[document.pk]))
    content = response.content.decode()

    assert "Veracidad 95%" in content
    # Warnings and the explicit approval action remain visible.
    assert "Confianza baja" in content
    assert f'action="/documents/{document.pk}/approve/"' in content


def test_review_ui_flag_disables_new_elements(client):
    """10.3 rollback: APP_REVIEW_UI_ENABLED=false restores the pre-change UI."""
    from django.conf import settings
    from django.test import override_settings

    viewer = make_user("lr", ("viewer",))
    document = make_document(paperless_document_id="88")
    add_page(document, text="page")
    make_certificate(document=document, veracity_score=0.9, format_score=0.8)
    client.force_login(viewer)

    with override_settings(APP={**settings.APP, "review_ui_enabled": False}):
        response = client.get(reverse("documents:list"))
        content = response.content.decode()
        assert "Veracidad" not in content
        assert "row-veracity-" not in content
        assert 'class="doc-thumb"' not in content
        assert 'class="icon-btn preview-btn"' not in content
        # Format badge and plain review link remain.
        assert "Formato" in content
        assert f'href="/documents/{document.pk}/"' in content

        response = client.get(reverse("documents:detail", args=[document.pk]))
        content = response.content.decode()
        assert "<h3>Veracidad</h3>" not in content
        assert "Veracidad 90%" not in content
