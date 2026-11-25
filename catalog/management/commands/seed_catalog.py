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
    ExamAlias,
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
        "aliases": ["French", "Francés", "Frances", "Français", "Francaise", "frangaise"],
    },
    {
        "code": "deu",
        "name": "German",
        "name_es": "Alemán",
        "aliases": ["German", "Alemán", "Aleman", "Deutsch", "Deutsche"],
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
        "date_order": "mdy",
        "aliases": ["ETS", "Educational Testing Service"],
        "exams": [
            ("TOEFL iBT", "eng"),
            ("TOEFL ITP", "eng"),
            ("TOEFL PBT", "eng"),
        ],
    },
    {
        "name": "TOEIC",
        "date_order": "mdy",
        "aliases": ["TOEIC", "Test of English for International Communication"],
        "exams": [
            ("TOEIC", "eng"),
            ("TOEIC Listening and Reading", "eng"),
            ("TOEIC Speaking and Writing", "eng"),
        ],
    },
    {
        "name": "Cambridge English",
        "date_order": "dmy",
        "aliases": [
            "Cambridge English",
            "Cambridge Assessment English",
            "Cambridge Assessment",
            "Cambridge University Press & Assessment",
            "Council of Europe, Cambridge University Press & Assessment",
            "Cambridge",
        ],
        "exams": [
            ("A2 Key", "eng", ["Key English Test", "KET"]),
            ("B1 Preliminary", "eng", ["Preliminary English Test", "PET"]),
            ("B2 First", "eng", ["First Certificate in English", "First Certificate", "FCE"]),
            (
                "C1 Advanced",
                "eng",
                [
                    "Advanced English",
                    "Certificate in Advanced English",
                    "Certificate in Advanced English / C1 Advanced",
                    "CAE",
                ],
            ),
            (
                "C2 Proficiency",
                "eng",
                ["Certificate of Proficiency in English", "CPE"],
            ),
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
        "date_order": "dmy",
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
        "date_order": "dmy",
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
        "date_order": "mdy",
        "aliases": ["Duolingo", "Duolingo English Test", "DET"],
        "exams": [("Duolingo English Test", "eng")],
    },
    {
        "name": "Trinity College London",
        "date_order": "dmy",
        "aliases": [
            "Trinity College London",
            "Trinity",
            "Trinity College London - Integrated Skills in English",
        ],
        "exams": [
            (
                "ISE",
                "eng",
                ["Integrated Skills in English", "Integrated Skills in English (ISE)"],
            ),
            ("GESE", "eng"),
            ("ISE 0", "eng"),
            ("ISE I", "eng"),
            ("ISE II", "eng"),
            ("ISE III", "eng"),
            ("ISE IV", "eng"),
        ]
        + [(f"GESE Grade {grade}", "eng") for grade in range(1, 13)]
        + [(f"SEW {level}", "eng") for level in ("B1", "B2", "B2+", "C1")],
    },
    {
        "name": "OET",
        "date_order": "dmy",
        "aliases": ["OET", "Occupational English Test"],
        "exams": [("OET", "eng")],
    },
    {
        "name": "France Éducation international",
        "date_order": "dmy",
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
        "date_order": "dmy",
        "aliases": [
            "CCI Paris Île-de-France",
            "CCI Paris Ile-de-France",
            "Chambre de Commerce et d'Industrie de Paris",
        ],
        "exams": [("TEF", "fra")]
        + [(f"DFP {level}", "fra") for level in ("A1", "A2", "B1", "B2", "C1", "C2")],
    },
    {
        "name": "Alliance Française",
        "date_order": "dmy",
        "aliases": ["Alliance Française", "Alliance Francaise"],
        "exams": [
            ("CEFP 1", "fra", ["Certificat d'Études de Français Pratique 1"]),
            ("CEFP 2", "fra", ["Certificat d'Études de Français Pratique 2"]),
            ("DS", "fra", ["Diplôme Supérieur d'Études Françaises Modernes"]),
            ("DHEF", "fra", ["Diplôme des Hautes Études Françaises"]),
        ],
    },
    {
        "name": "Diplômes d'Université",
        "date_order": "dmy",
        "aliases": ["Diplômes d'Université", "Diplomes d'Universite", "DU"],
        "exams": [
            (f"{family} {level}", "fra")
            for family in ("DUEF", "DULF")
            for level in ("A1", "A2", "B1", "B2", "C1", "C2")
        ]
        + [(f"CPLF {level}", "fra") for level in ("B1", "B2", "C1", "C2")]
        + [
            ("DEF B2", "fra"),
            ("DAEF C1", "fra"),
            ("DAEF C2", "fra"),
            ("DSEF C1", "fra"),
            ("DSEF C2", "fra"),
            ("DUSEF C2", "fra"),
        ],
    },
    {
        "name": "Goethe-Institut",
        "date_order": "dmy",
        "aliases": ["Goethe-Institut", "Goethe Institut", "Goethe"],
        "exams": [
            ("Start Deutsch 1", "deu"),
            ("Start Deutsch 2", "deu"),
            ("Zertifikat Deutsch", "deu", ["ZD", "Zertifikat Deutsch (ZD)"]),
            ("ZDJ", "deu", ["Zertifikat Deutsch für Jugendliche"]),
            ("DAF", "deu", ["Deutsch als Fremdsprache"]),
            ("GDS", "deu", ["Großes Deutsches Sprachdiplom"]),
            ("ZOP", "deu", ["Zentrale Oberstufenprüfung"]),
            ("KDS", "deu", ["Kleines Deutsches Sprachdiplom"]),
            ("BULATS", "deu"),
            ("Goethe-Zertifikat B1", "deu"),
            ("Goethe-Zertifikat B2", "deu"),
            ("Goethe-Zertifikat C1", "deu"),
            ("Goethe-Zertifikat C2", "deu"),
        ],
    },
    {
        "name": "telc gGmbH",
        "date_order": "dmy",
        "aliases": ["telc", "telc gGmbH", "The European Language Certificates"],
        "exams": [
            ("telc B1", "deu"),
            ("telc B2", "deu"),
            ("telc C1", "deu"),
            ("telc Deutsch A1", "deu"),
            ("telc Deutsch A2", "deu"),
            ("telc Deutsch B1", "deu"),
            ("telc Deutsch B2", "deu"),
            ("telc Deutsch B2-Beruf", "deu", ["Telc Deutsch B2 – Beruf"]),
            ("telc Deutsch C1", "deu"),
            ("telc Deutsch C2", "deu"),
            ("telc English A1", "eng"),
            ("telc English A2", "eng"),
            ("telc English B1", "eng"),
            ("telc English B2", "eng"),
            ("telc English C1", "eng"),
            ("telc English C2", "eng"),
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
            ("telc Português B1", "por"),
        ],
    },
    {
        "name": "TestDaF-Institut",
        "date_order": "dmy",
        "aliases": ["TestDaF", "TestDaF-Institut"],
        "exams": [("TestDaF", "deu")],
    },
    {
        "name": "ÖSD",
        "date_order": "dmy",
        "aliases": ["ÖSD", "OSD", "Österreichisches Sprachdiplom"],
        "exams": [
            (
                "ÖSD A1",
                "deu",
                ["A1 Grundstufe Deutsch 1", "GD1", "ÖSD GD1"],
            ),
            (
                "ÖSD A2",
                "deu",
                ["A2 Grundstufe Deutsch 2", "GD2", "ÖSD GD2"],
            ),
            ("ÖSD B1", "deu", ["B1 Zertifikat", "ZD", "ÖSD ZD"]),
            ("ÖSD B2", "deu", ["Mittelstufe Deutsch", "MD", "ÖSD MD"]),
            ("ÖSD C1", "deu", ["Oberstufe Deutsch", "OD", "ÖSD OD"]),
            ("ÖSD C2", "deu", ["Wirtschaftssprache Deutsch", "WD", "ÖSD WD"]),
        ],
    },
    {
        "name": "DSH",
        "date_order": "dmy",
        "aliases": ["DSH", "Deutsche Sprachprüfung für den Hochschulzugang"],
        "exams": [("DSH", "deu"), ("DSH-1", "deu"), ("DSH-2", "deu"), ("DSH-3", "deu")],
    },
    {
        "name": "g.a.s.t.",
        "date_order": "dmy",
        "aliases": ["g.a.s.t.", "gast", "DTZ"],
        "exams": [("DTZ", "deu")],
    },
    {
        "name": "Instituto Cervantes",
        "date_order": "dmy",
        "aliases": ["Instituto Cervantes", "Cervantes"],
        "exams": [("DELE", "spa")]
        + [(f"DELE {level}", "spa") for level in ("A1", "A2", "B1", "B2", "C1", "C2")],
    },
    {
        "name": "SIELE",
        "date_order": "dmy",
        "aliases": ["SIELE"],
        "exams": [("SIELE Global", "spa")],
    },
    {
        "name": "CELU",
        "date_order": "dmy",
        "aliases": ["CELU"],
        "exams": [("CELU", "spa")],
    },
    {
        "name": "Università per Stranieri di Siena",
        "date_order": "dmy",
        "aliases": [
            "Università per Stranieri di Siena",
            "Universita per Stranieri di Siena",
            "CILS",
        ],
        "exams": [
            ("CILS", "ita"),
            ("CILS Due-B2", "ita"),
            ("CILS Tre-C1", "ita"),
            ("CILS Quattro-C2", "ita"),
        ],
    },
    {
        "name": "Università per Stranieri di Perugia",
        "date_order": "dmy",
        "aliases": [
            "Università per Stranieri di Perugia",
            "Universita per Stranieri di Perugia",
            "CELI",
        ],
        "exams": [("CELI", "ita")]
        + [("CELI Impatto", "ita")]
        + [(f"CELI {level}", "ita") for level in range(1, 6)],
    },
    {
        "name": "Società Dante Alighieri",
        "date_order": "dmy",
        "aliases": ["Società Dante Alighieri", "Societa Dante Alighieri", "PLIDA"],
        "exams": [("PLIDA", "ita")]
        + [(f"PLIDA {level}", "ita") for level in ("A1", "A2", "B1", "B2", "C1", "C2")]
        + [("PLIDA Commerciale B2", "ita"), ("PLIDA Commerciale C1", "ita")],
    },
    {
        "name": "Università degli Studi Roma Tre",
        "date_order": "dmy",
        "aliases": [
            "Università degli Studi Roma Tre",
            "Universita degli Studi Roma Tre",
            "Cert.IT",
            "CertIT",
        ],
        "exams": [("Cert.IT", "ita"), ("Int IT", "ita"), ("IT", "ita")],
    },
    {
        "name": "CAPLE",
        "date_order": "dmy",
        "aliases": [
            "CAPLE",
            "Centro de Avaliação de Português Língua Estrangeira",
            "Universidade de Lisboa",
        ],
        "exams": [
            ("CAPLE", "por"),
            ("CAPLE ACESSO", "por", ["ACESSO", "Certificado de Acesso ao Português"]),
            ("CAPLE CIPLE", "por", ["CIPLE", "Certificado Inicial de Português Língua Estrangeira"]),
            ("CAPLE DEPLE", "por", ["DEPLE", "Diploma Elementar de Português Língua Estrangeira"]),
            ("CAPLE DIPLE", "por", ["DIPLE", "Diploma Intermédio de Português Língua Estrangeira"]),
            ("CAPLE DAPLE", "por", ["DAPLE", "Diploma Avançado de Português Língua Estrangeira"]),
            ("CAPLE DUPLE", "por", ["DUPLE", "Diploma Universitário de Português Língua Estrangeira"]),
        ],
    },
    {
        "name": "CELPE-Bras",
        "date_order": "dmy",
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
        "date_order": "dmy",
        "aliases": [
            "Oxford University Press",
            "University of Oxford, Oxford University Press",
            "Oxford",
            "Oxford Test of English",
        ],
        "exams": [("Oxford Test of English", "eng")],
    },
    {
        "name": "APTIS",
        "date_order": "dmy",
        "aliases": ["APTIS", "British Council"],
        "exams": [(f"APTIS {level}", "eng") for level in ("A1", "A2", "B1", "B2", "C1", "C2")],
    },
    {
        "name": "Anglia Ascentis",
        "date_order": "dmy",
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
        "date_order": "dmy",
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
        "date_order": "dmy",
        "aliases": ["esPro", "Universidad de Salamanca"],
        "exams": [("esPro", "spa")],
    },
    {
        "name": "CLES",
        "date_order": "dmy",
        "aliases": ["CLES", "Certificat de Compétences en Langues de l'Enseignement Supérieur"],
        "exams": [("CLES 1", "fra"), ("CLES 2", "fra"), ("CLES 3", "fra")],
    },
    {
        "name": "Alexander Pushkin",
        "date_order": "dmy",
        "aliases": ["Alexander Pushkin", "Pushkin", "TORFL", "TRKI"],
        "exams": [(f"TORFL {level}", "rus") for level in ("A1", "A2", "B1", "B2", "C1", "C2")],
    },
    {
        "name": "TRKI",
        "date_order": "dmy",
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
        "date_order": "dmy",
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
        "date_order": "dmy",
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
    # Entities from the UV L2 table that had no seed entry yet
    {
        "name": "AQA",
        "date_order": "dmy",
        "aliases": [
            "AQA",
            "Assessment and Qualifications Alliance",
            "AQA Qualifications",
        ],
        "exams": [
            ("JET Foundation", "eng"),
            ("JET 1", "eng"),
            ("JET 2", "eng"),
            ("JET 3", "eng"),
            ("JET 4", "eng"),
            ("SET 1", "eng"),
            ("SET 2", "eng"),
        ],
    },
    {
        "name": "TOLES",
        "date_order": "dmy",
        "aliases": ["TOLES", "Test of Legal English"],
        "exams": [
            ("TOLES Intermediate", "eng"),
            ("TOLES Pre-Advanced", "eng"),
            ("TOLES Upper Intermediate", "eng"),
        ],
    },
    {
        "name": "English Speaking Board",
        "date_order": "dmy",
        "aliases": ["English Speaking Board", "EAL/ESOL", "ESB"],
        "exams": [
            ("EAL/ESOL Entry 1", "eng"),
            ("EAL/ESOL Entry 2", "eng"),
            ("EAL/ESOL Entry 3", "eng"),
            ("EAL/ESOL Level 1", "eng"),
            ("EAL/ESOL Level 2", "eng"),
            ("EAL/ESOL Level 3", "eng"),
        ],
    },
    {
        "name": "University of Michigan",
        "date_order": "mdy",
        "aliases": [
            "University of Michigan",
            "Cambridge Michigan Language Assessments",
            "Michigan Language Assessments",
        ],
        "exams": [
            ("ECCE", "eng", ["Certificate of Competency in English"]),
            ("ECPE", "eng", ["Certificate of Proficiency in English (ECPE)"]),
        ],
    },
    {
        "name": "UNICERT",
        "date_order": "dmy",
        "aliases": ["UNICERT"],
        "exams": [
            ("UNICERT Basis", None),
            ("UNICERT Level 1", None),
            ("UNICERT Level 2", None),
            ("UNICERT Level 3", None),
            ("UNICERT Level 4", None),
        ],
    },
    {
        "name": "General Certificate of Secondary Education",
        "date_order": "dmy",
        "aliases": [
            "General Certificate of Secondary Education",
            "GCSE",
            "A-Level",
            "A Level",
        ],
        "exams": [
            ("GCSE Grades A-C", "eng"),
            ("GCSE Higher Pass Grades A-C", "eng"),
            ("A-Level", "eng"),
        ],
    },
    {
        "name": "EOI",
        "date_order": "dmy",
        "aliases": [
            "EOI",
            "Escola Oficial d'Idiomes",
            "Escoles Oficials d'Idiomes",
        ],
        "exams": [
            (
                "EOI Nivell C1",
                None,
                [
                    "certificación del nivel c1",
                    "certificat de nivell c1",
                    "certificado de nivel c1",
                ],
            ),
            (
                "EOI Nivell C2",
                None,
                [
                    "certificación del nivel c2",
                    "certificat de nivell c2",
                    "certificado de nivel c2",
                ],
            ),
        ],
    },
    {
        "name": "Ensenyaments d'idiomes",
        "date_order": "dmy",
        "aliases": [
            "Ensenyaments d'idiomes",
            "prova d'idiomes",
            "Prova de Coneixements Lingüístics",
        ],
        "exams": [("Certificat de prova d'idiomes", None)],
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
            entity_defaults: dict = {}
            if "date_order" in data:
                entity_defaults["date_order"] = data["date_order"]
            entity, _ = Entity.objects.update_or_create(
                name=data["name"], defaults=entity_defaults
            )
            for alias in data["aliases"]:
                EntityAlias.objects.get_or_create(
                    normalized_alias=normalize_catalog_text(alias),
                    defaults={"entity": entity, "alias": alias},
                )
            for exam_entry in data["exams"]:
                exam_name, language_code = exam_entry[0], exam_entry[1]
                exam_aliases = exam_entry[2] if len(exam_entry) > 2 else []
                exam, _ = Exam.objects.get_or_create(
                    entity=entity,
                    name=exam_name,
                    defaults={"language": language_by_code.get(language_code)},
                )
                exam_by_key[(entity.name, exam.name)] = exam
                for alias in exam_aliases:
                    ExamAlias.objects.get_or_create(
                        normalized_alias=normalize_catalog_text(alias),
                        defaults={"exam": exam, "alias": alias},
                    )

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
