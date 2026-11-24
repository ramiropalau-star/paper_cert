"""Configuration tests for Docker/ops artifacts (tasks 12.3, 12.6)."""

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent

EXPECTED_SERVICES = {"app", "ocr", "n8n", "paperless", "db", "redis", "ollama", "watcher"}
PUBLISHED_SERVICES = {"app", "n8n", "paperless"}


def _env_example_keys() -> set[str]:
    keys = set()
    for line in (ROOT / ".env.example").read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            keys.add(line.split("=", 1)[0].strip())
    return keys


def _settings_env_names() -> set[str]:
    source = (ROOT / "config" / "settings.py").read_text()
    names = set(re.findall(r'(?:source|environ|os\.environ)\.get\("([A-Z_]+)"', source))
    names |= set(
        re.findall(r'env_(?:int|float|bool|list)\(\s*(?:source|os\.environ),\s*"([A-Z_]+)"', source)
    )
    return names


def test_env_example_covers_every_settings_variable():
    documented = _env_example_keys()
    referenced = _settings_env_names()
    missing = referenced - documented
    assert not missing, f"Variables missing from .env.example: {sorted(missing)}"


def test_compose_yaml_parses_and_has_expected_services():
    compose = yaml.safe_load((ROOT / "compose.yaml").read_text())
    services = compose["services"]
    assert EXPECTED_SERVICES <= set(services)

    published = {name for name, svc in services.items() if svc.get("ports")}
    assert published == PUBLISHED_SERVICES

    for name, svc in services.items():
        assert "healthcheck" in svc, f"{name} lacks a healthcheck"
        assert "restart" in svc or name == "app"

    networks = {n for svc in services.values() for n in svc.get("networks", [])}
    assert networks == {"internal"}
    assert set(compose["volumes"]) >= {
        "postgres-data",
        "paperless-data",
        "paperless-media",
        "n8n-data",
        "ollama-models",
        "app-media",
        "reports",
    }


def test_compose_images_are_pinned():
    compose = yaml.safe_load((ROOT / "compose.yaml").read_text())
    for name, svc in compose["services"].items():
        image = svc.get("image")
        if image is None:
            continue  # built from source
        assert ":" in image, f"{name} image is not pinned: {image}"
        assert "latest" not in image


def test_compose_contains_no_secret_literals():
    compose = (ROOT / "compose.yaml").read_text()
    for line in compose.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        assert "change-me" not in stripped
        assert "password" not in stripped.lower() or "${" in stripped or "$${" in stripped


def test_app_dockerfile_is_hardened():
    dockerfile = (ROOT / "docker" / "app.Dockerfile").read_text()
    assert "USER 10001" in dockerfile or "USER app" in dockerfile
    assert "gunicorn" in dockerfile
    assert "HEALTHCHECK" in dockerfile
    assert dockerfile.count("FROM ") >= 2  # multi-stage
    assert "requirements-dev" not in dockerfile
    for line in dockerfile.splitlines():
        if line.strip().startswith("#"):
            continue
        assert "SECRET" not in line and "TOKEN" not in line


def test_ocr_dockerfile_is_complete():
    dockerfile = (ROOT / "ocr-service" / "Dockerfile").read_text()
    runtime = dockerfile.split("FROM base AS runtime", 1)[1].split("FROM", 1)[0]
    assert "USER" in dockerfile
    assert "HEALTHCHECK" in runtime
    assert "CMD" in runtime


def test_init_db_script_creates_sibling_databases():
    script = (ROOT / "docker" / "initdb" / "01-databases.sql").read_text()
    assert "paperless" in script and "n8n" in script


def test_bootstrap_command_exists():
    command = ROOT / "core" / "management" / "commands" / "bootstrap.py"
    assert command.is_file()
    assert "seed_catalog" in command.read_text()


def test_n8n_workflows_are_valid_json_with_stages():
    import json

    processing = json.loads((ROOT / "n8n" / "workflows" / "processing.json").read_text())
    names = {node["name"] for node in processing["nodes"]}
    assert any("Webhook" in n for n in names)
    assert any("text" in n.lower() for n in names)
    assert any("Extract" in n for n in names)
    assert any("Classify" in n for n in names)

    report = json.loads((ROOT / "n8n" / "workflows" / "report.json").read_text())
    report_names = {node["name"] for node in report["nodes"]}
    assert any("report" in n.lower() for n in report_names)
    urls = " ".join(str(node["parameters"].get("url", "")) for node in report["nodes"])
    assert "/internal/report-jobs/" in urls
