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
    "recovery_attempts_exhausted": (
        "Reintentos agotados",
        "El documento agotó los intentos automáticos de recuperación.",
    ),
}

BAND_LABELS = {"high": "Alta", "medium": "Media", "low": "Baja"}


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
