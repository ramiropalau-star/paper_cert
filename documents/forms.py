"""Forms for the review workflow."""

from django import forms

from catalog.models import CefrLevel, Entity, Exam, Language


class CertificateEditForm(forms.Form):
    student_name = forms.CharField(max_length=300, required=False)
    language_literal = forms.CharField(max_length=200, required=False)
    entity_literal = forms.CharField(max_length=300, required=False)
    issuing_body_literal = forms.CharField(max_length=300, required=False)
    test_center_literal = forms.CharField(max_length=300, required=False)
    exam_literal = forms.CharField(max_length=300, required=False)
    level_literal = forms.CharField(max_length=200, required=False)
    score_literal = forms.CharField(max_length=200, required=False)
    certificate_code = forms.CharField(max_length=200, required=False)
    cefr_level = forms.ChoiceField(choices=[("", "—")] + list(CefrLevel.choices), required=False)
    equivalence = forms.ChoiceField(choices=[("", "—")] + list(CefrLevel.choices), required=False)
    issue_date = forms.DateField(required=False)
    exam_date = forms.DateField(required=False)
    result_date = forms.DateField(required=False)
    detected_date = forms.DateField(required=False)
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
