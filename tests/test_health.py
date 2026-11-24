import json

from django.template.loader import render_to_string


def test_health_endpoint_returns_ok(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert json.loads(response.content) == {"status": "ok"}


def test_unknown_route_renders_error_template(client):
    response = client.get("/this-route-does-not-exist")
    assert response.status_code == 404
    template_names = [template.name for template in response.templates]
    assert "404.html" in template_names


def test_base_template_renders_brand():
    html = render_to_string("base.html")
    assert "Certificados de idiomas" in html
    assert "app.css" in html
