"""Presentation helpers for the review screen.

Maps stored reason codes to human labels and explanations, and formats
extraction confidence as a percentage with a quality band. Raw codes stay
available for diagnostics but are never the primary text.
"""

UNKNOWN_REASON = ("Revisión adicional", "El documento necesita una revisión manual adicional.")

REVIEW_REASON_DETAILS = {
    "insufficient_text": (
        "Texto insuficiente",
        "No se pudo extraer texto suficiente del documento para procesarlo.",
    ),
    "low_ocr_confidence": (
        "OCR de baja confianza",
        "El reconocimiento de texto produjo resultados poco confiables.",
    ),
    "ocr_failed": (
        "OCR fallido",
        "El servicio de OCR no pudo procesar el documento.",
    ),
    "incomplete_ocr": (
        "OCR incompleto",
        "Algunas páginas no se pudieron procesar con OCR.",
    ),
    "original_unavailable": (
        "Original no disponible",
        "No se pudo descargar el archivo original desde Paperless.",
    ),
    "manual_label_failed": (
        "Clasificación manual fallida",
        "La clasificación de la etiqueta en Paperless no se pudo aplicar.",
    ),
    "unreadable": (
        "Documento ilegible",
        "El documento no contiene texto legible para el pipeline.",
    ),
    "timeout": (
        "Tiempo agotado",
        "Una etapa del procesamiento excedió el tiempo límite.",
    ),
    "empty_file": (
        "Archivo vacío",
        "El archivo original está vacío o no contiene datos.",
    ),
    "unsupported_file": (
        "Tipo de archivo no soportado",
        "El formato del archivo no puede ser procesado por el pipeline.",
    ),
    "too_many_pages": (
        "Demasiadas páginas",
        "El documento supera el límite de páginas permitido.",
    ),
    "input_too_large": (
        "Entrada demasiado grande",
        "El texto extraído supera el tamaño máximo que acepta el modelo.",
    ),
    "missing_text": (
        "Sin texto para extraer",
        "No hay texto disponible para la extracción de datos.",
    ),
    "model_unavailable": (
        "Modelo no disponible",
        "El modelo de extracción no respondió o no está configurado.",
    ),
    "invalid_extraction": (
        "Extracción inválida",
        "La salida del modelo no superó las validaciones del pipeline.",
    ),
    "non_certificate": (
        "No es un certificado",
        "El documento no parece ser un certificado de idioma.",
    ),
    "multiple_certificates": (
        "Posibles múltiples certificados",
        "El documento parece contener más de un certificado.",
    ),
    "missing_essential_fields": (
        "Faltan campos obligatorios",
        "La extracción no produjo todos los campos esenciales.",
    ),
    "unknown_language": (
        "Idioma no identificado",
        "El idioma no coincide con el catálogo; revisá el texto literal.",
    ),
    "unknown_entity": (
        "Entidad pendiente de identificar",
        "La entidad certificadora no coincide con el catálogo.",
    ),
    "ambiguous_date": (
        "Fecha ambigua",
        "Una fecha detectada no tiene una categoría clara.",
    ),
    "low_confidence": (
        "Confianza baja",
        "La confianza de la extracción está por debajo del umbral.",
    ),
    "equivalence_not_found": (
        "Equivalencia no encontrada",
        "No se encontró equivalencia UV L2 para el nivel declarado.",
    ),
    "format_mismatch": (
        "Formato no reconocido",
        "El documento no coincide con el formato conocido del organismo emisor.",
    ),
    "entity_mismatch": (
        "Entidad detectada en discrepancia",
        "El emisor detectado antes de la extracción difiere del resuelto por clasificación; puede haberse re-extraído con el perfil del emisor resuelto.",
    ),
    "source_mismatch": (
        "Discrepancia con el documento fuente",
        "La verificación en origen devolvió campos que no coinciden con los extraídos; revisá los datos antes de aprobar.",
    ),
    "possible_duplicate": (
        "Posible duplicado",
        "Otro certificado vivo coincide con este en identidad (código o alumno/examen/fecha); verificá antes de aprobar.",
    ),
    "cefr_discrepancy": (
        "Discrepancia de nivel CEFR",
        "El nivel CEFR impreso en el certificado difiere del nivel resuelto por las reglas del examen; verificá cuál es el correcto.",
    ),
    "recovery_attempts_exhausted": (
        "Reintentos agotados",
        "El documento agotó los intentos automáticos de recuperación.",
    ),
}

BAND_LABELS = {"high": "Alta", "medium": "Media", "low": "Baja"}

# Veracity bands: a review aid only, never an approval signal.
VERACITY_BANDS = ((0.75, "high"), (0.45, "medium"), (0.0, "low"))

VERACITY_COMPONENT_FALLBACK = "Componente de veracidad"


def veracity_band(score) -> str | None:
    """Return high/medium/low for a 0-1 veracity score, else None."""
    if score is None:
        return None
    try:
        value = float(score)
    except (TypeError, ValueError):
        return None
    value = max(0.0, min(1.0, value))
    for threshold, band in VERACITY_BANDS:
        if value >= threshold:
            return band
    return "low"


def veracity_display(score):
    """Numeric veracity with band, or None when no score was computed."""
    band = veracity_band(score)
    if band is None:
        return None
    value = max(0.0, min(1.0, float(score)))
    return {
        "percent": int(round(value * 100)),
        "raw": f"{value:.2f}",
        "band": band,
        "band_label": BAND_LABELS[band],
    }


def veracity_breakdown_items(components: dict | None) -> list[dict]:
    """Human-labeled veracity components for the review detail.

    Unknown component codes degrade to a generic label; the raw code is
    never the primary text. The weakest component is flagged.
    """
    raw = (components or {}).get("components") or {}
    items = []
    for name, data in raw.items():
        if not isinstance(data, dict):
            continue
        try:
            value = float(data.get("value"))
        except (TypeError, ValueError):
            value = 0.0
        label = str(data.get("label") or "").strip() or VERACITY_COMPONENT_FALLBACK
        items.append(
            {
                "name": str(name),
                "label": label,
                "value": round(max(0.0, min(1.0, value)), 4),
                "percent": int(round(max(0.0, min(1.0, value)) * 100)),
            }
        )
    if items:
        weakest = min(items, key=lambda item: item["value"])
        for item in items:
            item["weakest"] = item is weakest
    return items


def review_reason_items(reasons) -> list[dict]:
    """Return de-duplicated reason items with label, explanation, and code."""
    items: list[dict] = []
    seen: set[str] = set()
    for reason in reasons or []:
        code = str(reason)
        if code in seen:
            continue
        seen.add(code)
        known = code in REVIEW_REASON_DETAILS
        label, explanation = REVIEW_REASON_DETAILS.get(code, UNKNOWN_REASON)
        items.append(
            {
                "code": code,
                "label": label,
                "explanation": explanation,
                "known": known,
            }
        )
    return items


def confidence_display(value):
    """Return a dict with percent, raw, and band, or None for missing values."""
    if value is None:
        return None
    try:
        fraction = float(value)
    except (TypeError, ValueError):
        return None
    if fraction > 1:
        fraction = fraction / 100
    fraction = max(0.0, min(1.0, fraction))
    if fraction >= 0.85:
        band = "high"
    elif fraction >= 0.60:
        band = "medium"
    else:
        band = "low"
    return {
        "percent": int(round(fraction * 100)),
        "raw": f"{fraction:.2f}",
        "band": band,
        "band_label": BAND_LABELS[band],
    }
