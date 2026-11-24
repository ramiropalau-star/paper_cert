from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from catalog.equivalences import EQUIVALENCES
from catalog.models import (
    CefrConversionRule,
    Entity,
    EntityAlias,
    Equivalence,
    Exam,
    Language,
    LanguageAlias,
)
from catalog.normalization import normalize_catalog_text

LANGUAGES = [
    {
        "code": "eng",
        "name": "English",
        "name_es": "Inglés",
        "aliases": ["English", "Inglés", "Ingles"],
    },
    {
        "code": "fra",
        "name": "French",
        "name_es": "Francés",
        "aliases": ["French", "Francés", "Frances"],
    },
    {
        "code": "deu",
        "name": "German",
        "name_es": "Alemán",
        "aliases": ["German", "Alemán", "Aleman"],
    },
    {
        "code": "spa",
        "name": "Spanish",
        "name_es": "Español",
        "aliases": ["Spanish", "Español", "Espanol"],
    },
    {
        "code": "ita",
        "name": "Italian",
        "name_es": "Italiano",
        "aliases": ["Italian", "Italiano"],
    },
    {
        "code": "por",
        "name": "Portuguese",
        "name_es": "Portugués",
        "aliases": ["Portuguese", "Portugués", "Portugues"],
    },
    {
        "code": "rus",
        "name": "Russian",
        "name_es": "Ruso",
        "aliases": ["Russian", "Ruso", "Русский"],
    },
    {
        "code": "zho",
        "name": "Chinese",
        "name_es": "Chino",
        "aliases": ["Chinese", "Chino", "Mandarin"],
    },
    {
        "code": "val",
        "name": "Valencian",
        "name_es": "Valenciano",
        "aliases": [
            "Valencian",
            "Valenciano",
            "Catalan",
            "Català",
            "Catalan / Valencian",
            "Valencià",
        ],
    },
]

ENTITIES = [
    {
        "name": "ETS",
        "aliases": ["ETS", "Educational Testing Service"],
        "exams": [
            ("TOEFL iBT", "eng"),
            ("TOEFL ITP", "eng"),
            ("TOEFL PBT", "eng"),
        ],
    },
    {
        "name": "TOEIC",
        "aliases": ["TOEIC"],
        "exams": [("TOEIC Listening and Reading", "eng"), ("TOEIC Speaking and Writing", "eng")],
    },
    {
        "name": "Cambridge English",
        "aliases": [
            "Cambridge English",
            "Cambridge Assessment English",
            "Cambridge",
        ],
        "exams": [
            ("A2 Key", "eng"),
            ("B1 Preliminary", "eng"),
            ("B2 First", "eng"),
            ("C1 Advanced", "eng"),
            ("C2 Proficiency", "eng"),
            ("BEC Preliminary", "eng"),
            ("BEC Vantage", "eng"),
            ("BEC Higher", "eng"),
            ("CELS Preliminary", "eng"),
            ("CELS Vantage", "eng"),
            ("CELS Higher", "eng"),
            ("Linguaskill A1", "eng"),
            ("Linguaskill A2", "eng"),
            ("Linguaskill B1", "eng"),
            ("Linguaskill B2", "eng"),
            ("Linguaskill C1", "eng"),
            ("Linguaskill C2", "eng"),
            ("BULATS", "eng"),
        ],
    },
    {
        "name": "IELTS",
        "aliases": ["IELTS", "International English Language Testing System"],
        "exams": [("IELTS Academic", "eng"), ("IELTS General Training", "eng")],
    },
    {
        "name": "Pearson",
        "aliases": ["Pearson", "Pearson PTE", "PTE"],
        "exams": [
            ("PTE Academic", "eng"),
            ("PTE General", "eng"),
            ("PTE General Level A1", "eng"),
            ("PTE General Level 1", "eng"),
            ("PTE General Level 2", "eng"),
            ("PTE General Level 3", "eng"),
            ("PTE General Level 4", "eng"),
            ("PTE General Level 5", "eng"),
        ],
    },
    {
        "name": "LanguageCert",
        "aliases": ["LanguageCert", "Language Cert"],
        "exams": [
            ("LanguageCert International ESOL", "eng"),
            ("LanguageCert Academic", "eng"),
            ("LanguageCert Access A2", "eng"),
            ("LanguageCert Achiever B1", "eng"),
            ("LanguageCert Communicator B2", "eng"),
            ("LanguageCert Expert C1", "eng"),
            ("LanguageCert Mastery C2", "eng"),
        ],
    },
    {
        "name": "Duolingo English Test",
        "aliases": ["Duolingo", "Duolingo English Test", "DET"],
        "exams": [("Duolingo English Test", "eng")],
    },
    {
        "name": "Trinity College London",
        "aliases": ["Trinity College London", "Trinity"],
        "exams": [
            ("ISE", "eng"),
            ("GESE", "eng"),
            ("ISE 0", "eng"),
            ("ISE I", "eng"),
            ("ISE II", "eng"),
            ("ISE III", "eng"),
            ("ISE IV", "eng"),
        ],
    },
    {
        "name": "OET",
        "aliases": ["OET", "Occupational English Test"],
        "exams": [("OET", "eng")],
    },
    {
        "name": "France Éducation international",
        "aliases": [
            "France Éducation international",
            "France Education International",
            "FEI",
            "CIEP",
        ],
        "exams": [
            ("DELF", "fra"),
            ("DALF", "fra"),
            ("TCF", "fra"),
            ("DELF A1", "fra"),
            ("DELF A2", "fra"),
            ("DELF B1", "fra"),
            ("DELF B2", "fra"),
            ("DALF C1", "fra"),
            ("DALF C2", "fra"),
        ],
    },
    {
        "name": "CCI Paris Île-de-France",
        "aliases": [
            "CCI Paris Île-de-France",
            "CCI Paris Ile-de-France",
            "Chambre de Commerce et d'Industrie de Paris",
        ],
        "exams": [("TEF", "fra")],
    },
    {
        "name": "Goethe-Institut",
        "aliases": ["Goethe-Institut", "Goethe Institut", "Goethe"],
        "exams": [
            ("Goethe-Zertifikat B1", "deu"),
            ("Goethe-Zertifikat B2", "deu"),
            ("Goethe-Zertifikat C1", "deu"),
            ("Goethe-Zertifikat C2", "deu"),
        ],
    },
    {
        "name": "telc gGmbH",
        "aliases": ["telc", "telc gGmbH"],
        "exams": [
            ("telc B1", "deu"),
            ("telc B2", "deu"),
            ("telc C1", "deu"),
            ("telc Deutsch A1", "deu"),
            ("telc Deutsch A2", "deu"),
            ("telc Deutsch B2", "deu"),
            ("telc Deutsch C1", "deu"),
            ("telc Deutsch C2", "deu"),
            ("telc Français A1", "fra"),
            ("telc Français A2", "fra"),
            ("telc Français B1", "fra"),
            ("telc Français B2", "fra"),
            ("telc Français C1", "fra"),
            ("telc Français C2", "fra"),
            ("telc Italiano A1", "ita"),
            ("telc Italiano A2", "ita"),
            ("telc Italiano B1", "ita"),
            ("telc Italiano B2", "ita"),
            ("telc Italiano C1", "ita"),
            ("telc Italiano C2", "ita"),
        ],
    },
    {
        "name": "TestDaF-Institut",
        "aliases": ["TestDaF", "TestDaF-Institut"],
        "exams": [("TestDaF", "deu")],
    },
    {
        "name": "ÖSD",
        "aliases": ["ÖSD", "OSD", "Österreichisches Sprachdiplom"],
        "exams": [
            ("ÖSD B1", "deu"),
            ("ÖSD B2", "deu"),
            ("ÖSD C1", "deu"),
            ("ÖSD A1", "deu"),
            ("ÖSD A2", "deu"),
            ("ÖSD C2", "deu"),
        ],
    },
    {
        "name": "DSH",
        "aliases": ["DSH", "Deutsche Sprachprüfung für den Hochschulzugang"],
        "exams": [("DSH", "deu"), ("DSH-1", "deu"), ("DSH-2", "deu"), ("DSH-3", "deu")],
    },
    {
        "name": "g.a.s.t.",
        "aliases": ["g.a.s.t.", "gast", "DTZ"],
        "exams": [("DTZ", "deu")],
    },
    {
        "name": "Instituto Cervantes",
        "aliases": ["Instituto Cervantes", "Cervantes"],
        "exams": [("DELE", "spa")]
        + [(f"DELE {level}", "spa") for level in ("A1", "A2", "B1", "B2", "C1", "C2")],
    },
    {
        "name": "SIELE",
        "aliases": ["SIELE"],
        "exams": [("SIELE Global", "spa")],
    },
    {
        "name": "CELU",
        "aliases": ["CELU"],
        "exams": [("CELU", "spa")],
    },
    {
        "name": "Università per Stranieri di Siena",
        "aliases": [
            "Università per Stranieri di Siena",
            "Universita per Stranieri di Siena",
            "CILS",
        ],
        "exams": [("CILS", "ita")],
    },
    {
        "name": "Università per Stranieri di Perugia",
        "aliases": [
            "Università per Stranieri di Perugia",
            "Universita per Stranieri di Perugia",
            "CELI",
        ],
        "exams": [("CELI", "ita")],
    },
    {
        "name": "Società Dante Alighieri",
        "aliases": ["Società Dante Alighieri", "Societa Dante Alighieri", "PLIDA"],
        "exams": [("PLIDA", "ita")]
        + [(f"PLIDA {level}", "ita") for level in ("A1", "A2", "B1", "B2", "C1", "C2")],
    },
    {
        "name": "Università degli Studi Roma Tre",
        "aliases": [
            "Università degli Studi Roma Tre",
            "Universita degli Studi Roma Tre",
            "Cert.IT",
            "CertIT",
        ],
        "exams": [("Cert.IT", "ita")],
    },
    {
        "name": "CAPLE",
        "aliases": ["CAPLE", "Centro de Avaliação de Português Língua Estrangeira"],
        "exams": [
            ("CAPLE", "por"),
            ("CAPLE ACESSO", "por"),
            ("CAPLE CIPLE", "por"),
            ("CAPLE DEPLE", "por"),
            ("CAPLE DIPLE", "por"),
            ("CAPLE DAPLE", "por"),
            ("CAPLE DUPLE", "por"),
        ],
    },
    {
        "name": "CELPE-Bras",
        "aliases": ["CELPE-Bras", "CELPE Bras", "INEP"],
        "exams": [
            ("CELPE-Bras", "por"),
            ("CELPE-Bras Intermediário", "por"),
            ("CELPE-Bras Intermediário Superior", "por"),
            ("CELPE-Bras Avançado", "por"),
            ("CELPE-Bras Avançado Superior", "por"),
        ],
    },
    # Entities from the UV L2 equivalence table
    {
        "name": "Oxford University Press",
        "aliases": ["Oxford University Press", "Oxford", "Oxford Test of English"],
        "exams": [("Oxford Test of English", "eng")],
    },
    {
        "name": "APTIS",
        "aliases": ["APTIS", "British Council"],
        "exams": [(f"APTIS {level}", "eng") for level in ("A1", "A2", "B1", "B2", "C1", "C2")],
    },
    {
        "name": "Anglia Ascentis",
        "aliases": ["Anglia", "Anglia Ascentis", "Anglia ESOL"],
        "exams": [
            ("Anglia Preliminary", "eng"),
            ("Anglia Elementary", "eng"),
            ("Anglia Intermediate", "eng"),
            ("Anglia Advanced", "eng"),
            ("Anglia Proficiency", "eng"),
            ("Anglia Masters", "eng"),
        ],
    },
    {
        "name": "Edexcel",
        "aliases": ["Edexcel", "Pearson Edexcel"],
        "exams": [
            ("Edexcel Entry 1", "eng"),
            ("Edexcel Entry 2", "eng"),
            ("Edexcel Entry 3", "eng"),
            ("Edexcel Level 1", "eng"),
            ("Edexcel Level 2", "eng"),
            ("Edexcel Level 3", "eng"),
        ],
    },
    {
        "name": "Universidad de Salamanca esPro",
        "aliases": ["esPro", "Universidad de Salamanca"],
        "exams": [("esPro", "spa")],
    },
    {
        "name": "CLES",
        "aliases": ["CLES", "Certificat de Compétences en Langues de l'Enseignement Supérieur"],
        "exams": [("CLES 1", "fra"), ("CLES 2", "fra"), ("CLES 3", "fra")],
    },
    {
        "name": "Alexander Pushkin",
        "aliases": ["Alexander Pushkin", "Pushkin", "TORFL", "TRKI"],
        "exams": [(f"TORFL {level}", "rus") for level in ("A1", "A2", "B1", "B2", "C1", "C2")],
    },
    {
        "name": "TRKI",
        "aliases": ["TRKI", "Test of Russian as a Foreign Language"],
        "exams": [
            ("TRKI E", "rus"),
            ("TRKI B", "rus"),
            ("TRKI 1", "rus"),
            ("TRKI 2", "rus"),
            ("TRKI 3", "rus"),
            ("TRKI 4", "rus"),
        ],
    },
    {
        "name": "Hanban",
        "aliases": ["Hanban", "HSK", "Confucius Institute"],
        "exams": [
            ("HSK I", "zho"),
            ("HSK II", "zho"),
            ("HSK III", "zho"),
            ("HSK IV", "zho"),
            ("HSK V", "zho"),
            ("HSK VI", "zho"),
            ("HSKK-E", "zho"),
            ("HSKK-I", "zho"),
            ("HSKK-A", "zho"),
        ],
    },
    {
        "name": "Junta Qualificadora de Coneixements de València",
        "aliases": [
            "Junta Qualificadora de Coneixements de València",
            "Junta Qualificadora de Coneixements de Valencia",
            "La Junta Qualificadora de Coneixements de València",
            "La Junta Qualificadora de Coneixements de Valencia",
            "Junta Qualificadora de Coneixements",
            "JVLC",
        ],
        "exams": [
            ("Certificat Oficial Administratiu de Coneixements de Valencia", "val"),
            ("Certificat de Valencià", "val"),
            ("Nivell Bàsic de Valencià", "val"),
            ("Nivell Mitjà de Valencià", "val"),
            ("Nivell Superior de Valencià", "val"),
        ],
    },
]

CEFR_PLACEHOLDERS = [
    (
        "IELTS",
        "IELTS Academic",
        Decimal("7.00"),
        Decimal("8.00"),
        "C1",
        "Placeholder band mapping; requires institutional approval before activation.",
    ),
    (
        "Cambridge English",
        "C1 Advanced",
        Decimal("180.00"),
        Decimal("199.00"),
        "C1",
        "Placeholder Cambridge English Scale mapping; requires institutional approval before activation.",
    ),
]


class Command(BaseCommand):
    help = "Seed the language, entity, exam, alias, and CEFR placeholder catalog."

    @transaction.atomic
    def handle(self, *args, **options):
        language_by_code: dict[str, Language] = {}
        for data in LANGUAGES:
            language, _ = Language.objects.get_or_create(
                code=data["code"],
                defaults={"name": data["name"], "name_es": data["name_es"]},
            )
            language_by_code[data["code"]] = language
            for alias in data["aliases"]:
                LanguageAlias.objects.get_or_create(
                    normalized_alias=normalize_catalog_text(alias),
                    defaults={"language": language, "alias": alias},
                )

        exam_by_key: dict[tuple[str, str], Exam] = {}
        for data in ENTITIES:
            entity, _ = Entity.objects.get_or_create(name=data["name"])
            for alias in data["aliases"]:
                EntityAlias.objects.get_or_create(
                    normalized_alias=normalize_catalog_text(alias),
                    defaults={"entity": entity, "alias": alias},
                )
            for exam_name, language_code in data["exams"]:
                exam, _ = Exam.objects.get_or_create(
                    entity=entity,
                    name=exam_name,
                    defaults={"language": language_by_code[language_code]},
                )
                exam_by_key[(entity.name, exam.name)] = exam

        for entity_name, exam_name, score_min, score_max, level, reference in CEFR_PLACEHOLDERS:
            exam = exam_by_key.get((entity_name, exam_name))
            if exam is None:
                continue
            CefrConversionRule.objects.get_or_create(
                exam=exam,
                score_min=score_min,
                score_max=score_max,
                cefr_level=level,
                defaults={"reference": reference, "is_active": False},
            )

        equivalence_count = 0
        for entity_name, exam_name, score_min, score_max, level in EQUIVALENCES:
            exam = exam_by_key.get((entity_name, exam_name))
            if exam is None:
                continue
            _, created = Equivalence.objects.get_or_create(
                exam=exam,
                score_min=score_min,
                score_max=score_max,
                defaults={"accredited_level": level},
            )
            equivalence_count += created

        self.stdout.write(
            self.style.SUCCESS(
                "Catalog seeded: "
                f"{Language.objects.count()} languages, "
                f"{Entity.objects.count()} entities, "
                f"{Exam.objects.count()} exams, "
                f"{CefrConversionRule.objects.count()} CEFR rules, "
                f"{equivalence_count} new UV equivalences."
            )
        )
