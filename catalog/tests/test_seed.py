from io import StringIO

import pytest
from django.core.management import call_command

from catalog.models import (
    CefrConversionRule,
    Entity,
    EntityAlias,
    Exam,
    Language,
    LanguageAlias,
)

pytestmark = pytest.mark.django_db


def run_seed() -> str:
    output = StringIO()
    call_command("seed_catalog", stdout=output)
    return output.getvalue()


def test_seed_catalog_is_idempotent_and_covers_required_entities():
    run_seed()
    counts = (
        Language.objects.count(),
        LanguageAlias.objects.count(),
        Entity.objects.count(),
        EntityAlias.objects.count(),
        Exam.objects.count(),
        CefrConversionRule.objects.count(),
    )

    run_seed()

    assert counts == (
        Language.objects.count(),
        LanguageAlias.objects.count(),
        Entity.objects.count(),
        EntityAlias.objects.count(),
        Exam.objects.count(),
        CefrConversionRule.objects.count(),
    )
    assert counts[0] == 9
    assert counts[1] >= 14
    assert counts[2] == 36
    assert counts[3] >= 40
    assert counts[4] == 175
    assert counts[5] == 2

    required_entities = [
        "ETS",
        "TOEIC",
        "Cambridge English",
        "IELTS",
        "Pearson",
        "LanguageCert",
        "Duolingo English Test",
        "Trinity College London",
        "OET",
        "France Éducation international",
        "CCI Paris Île-de-France",
        "Goethe-Institut",
        "telc gGmbH",
        "TestDaF-Institut",
        "ÖSD",
        "DSH",
        "g.a.s.t.",
        "Instituto Cervantes",
        "SIELE",
        "CELU",
        "Università per Stranieri di Siena",
        "Università per Stranieri di Perugia",
        "Società Dante Alighieri",
        "Università degli Studi Roma Tre",
        "CAPLE",
        "CELPE-Bras",
    ]
    assert set(required_entities) <= set(Entity.objects.values_list("name", flat=True))

    required_exams = {
        "TOEFL iBT",
        "TOEFL ITP",
        "TOEIC Listening and Reading",
        "TOEIC Speaking and Writing",
        "A2 Key",
        "B1 Preliminary",
        "B2 First",
        "C1 Advanced",
        "C2 Proficiency",
        "IELTS Academic",
        "IELTS General Training",
        "PTE Academic",
        "PTE General",
        "LanguageCert International ESOL",
        "LanguageCert Academic",
        "Duolingo English Test",
        "ISE",
        "GESE",
        "OET",
        "DELF",
        "DALF",
        "TCF",
        "TEF",
        "Goethe-Zertifikat B1",
        "Goethe-Zertifikat B2",
        "Goethe-Zertifikat C1",
        "Goethe-Zertifikat C2",
        "telc B1",
        "telc B2",
        "telc C1",
        "TestDaF",
        "ÖSD B1",
        "ÖSD B2",
        "ÖSD C1",
        "DSH",
        "DTZ",
        "DELE",
        "SIELE Global",
        "CELU",
        "CILS",
        "CELI",
        "PLIDA",
        "Cert.IT",
        "CAPLE",
        "CELPE-Bras",
    }
    assert required_exams <= set(Exam.objects.values_list("name", flat=True))

    assert EntityAlias.objects.filter(normalized_alias="educational testing service").exists()
    assert EntityAlias.objects.filter(normalized_alias="goethe institut").exists()
    assert EntityAlias.objects.filter(normalized_alias="ciep").exists()
    assert not CefrConversionRule.objects.effective().exists()
