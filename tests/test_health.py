import json

import pytest
from django.template.loader import render_to_string


def test_health_endpoint_returns_ok(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert json.loads(response.content) == {"status": "ok"}


@pytest.mark.django_db
def test_readyz_returns_ready_when_database_is_up(client):
    response = client.get("/readyz")
    assert response.status_code == 200
    assert json.loads(response.content) == {"status": "ready"}


@pytest.mark.django_db
def test_readyz_returns_503_when_database_is_down(client, monkeypatch):
    from django.db import connection

    def boom():
        raise ConnectionError("db down")

    monkeypatch.setattr(connection, "cursor", boom)
    response = client.get("/readyz")
    assert response.status_code == 503
    assert json.loads(response.content) == {"status": "unavailable"}


def test_healthz_stays_up_when_database_is_down(client, monkeypatch):
    from django.db import connection

    def boom():
        raise ConnectionError("db down")

    monkeypatch.setattr(connection, "cursor", boom)
    response = client.get("/healthz")
    assert response.status_code == 200


def test_unknown_route_renders_error_template(client):
    response = client.get("/this-route-does-not-exist")
    assert response.status_code == 404
    template_names = [template.name for template in response.templates]
    assert "404.html" in template_names


def test_base_template_renders_brand():
    html = render_to_string("base.html")
    assert "Certificados de idiomas" in html
    assert "app.css" in html
