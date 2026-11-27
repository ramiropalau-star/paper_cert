"""Forms for the review workflow."""

from django import forms

from catalog.models import CefrLevel, Entity, Exam, Language


def _text_field(**kwargs) -> forms.CharField:
    return forms.CharField(
        widget=forms.TextInput(attrs={"placeholder": kwargs.pop("placeholder")}), **kwargs
    )


class CertificateEditForm(forms.Form):
    student_name = _text_field(max_length=300, required=False, placeholder="Nombre y apellidos")
    language_literal = _text_field(
        max_length=200, required=False, placeholder="Idioma tal como aparece en el certificado"
    )
    entity_literal = _text_field(
        max_length=300, required=False, placeholder="Entidad certificadora tal como aparece"
    )
    issuing_body_literal = _text_field(
        max_length=300, required=False, placeholder="Organismo emisor"
    )
    test_center_literal = _text_field(
        max_length=300, required=False, placeholder="Centro de examen"
    )
    exam_literal = _text_field(max_length=300, required=False, placeholder="Examen o certificación")
    level_literal = _text_field(
        max_length=200, required=False, placeholder="Nivel literal, p. ej. B2"
    )
    score_literal = _text_field(
        max_length=200, required=False, placeholder="Puntuación, p. ej. 180"
    )
    certificate_code = _text_field(
        max_length=200, required=False, placeholder="Código del certificado"
    )
    cefr_level = forms.ChoiceField(choices=[("", "—")] + list(CefrLevel.choices), required=False)
    equivalence = forms.ChoiceField(choices=[("", "—")] + list(CefrLevel.choices), required=False)
    date_widget = forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"})
    issue_date = forms.DateField(required=False, widget=date_widget)
    exam_date = forms.DateField(required=False, widget=date_widget)
    result_date = forms.DateField(required=False, widget=date_widget)
    detected_date = forms.DateField(required=False, widget=date_widget)
    language = forms.ModelChoiceField(
        queryset=Language.objects.filter(is_active=True), required=False
    )
    entity = forms.ModelChoiceField(queryset=Entity.objects.filter(is_active=True), required=False)
    exam = forms.ModelChoiceField(queryset=Exam.objects.filter(is_active=True), required=False)

    def clean_cefr_level(self):
        return self.cleaned_data["cefr_level"] or ""

    def clean_equivalence(self):
        return self.cleaned_data["equivalence"] or ""

    def to_certificate_values(self) -> dict:
        """Map form fields onto certificate attributes for the review service."""
        cleaned = self.cleaned_data
        return {
            "student_name": cleaned["student_name"].strip(),
            "language_literal": cleaned["language_literal"].strip(),
            "entity_literal": cleaned["entity_literal"].strip(),
            "issuing_body_literal": cleaned["issuing_body_literal"].strip(),
            "test_center_literal": cleaned["test_center_literal"].strip(),
            "exam_literal": cleaned["exam_literal"].strip(),
            "level_literal": cleaned["level_literal"].strip(),
            "score_literal": cleaned["score_literal"].strip(),
            "certificate_code": cleaned["certificate_code"].strip(),
            "cefr_level": cleaned["cefr_level"],
            "equivalence": cleaned["equivalence"],
            "issue_date": cleaned["issue_date"],
            "exam_date": cleaned["exam_date"],
            "result_date": cleaned["result_date"],
            "detected_date": cleaned["detected_date"],
            "language_id": cleaned["language"],
            "entity_id": cleaned["entity"],
            "exam_id": cleaned["exam"],
        }
