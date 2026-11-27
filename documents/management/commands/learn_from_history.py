"""``learn_from_history`` — seed catalog knowledge from approved certificates.

Replays catalog learning and format-profile learning over every approved or
validated certificate. Idempotent: aliases, exams, equivalences, and CEFR
rule candidates are only created when missing, and format profiles are
recomputed from the full cohort each run.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from documents.models import Certificate, ReviewEvent
from documents.services.format_profile import learn_format_profile
from documents.services.learning import learn_from_certificate

LEARNED_STATUSES = (
    Certificate.ReviewStatus.APPROVED,
    Certificate.ReviewStatus.VALIDATED,
)


class _DryRun(Exception):
    pass


def _outcome_is_empty(outcome: dict) -> bool:
    return not any(
        outcome.get(key)
        for key in (
            "aliases_created",
            "exams_created",
            "equivalences_created",
            "cefr_rules_created",
            "conflicts",
        )
    )


class Command(BaseCommand):
    help = (
        "Learn catalog aliases, rules, and format profiles from "
        "already-approved/validated certificates."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be learned without writing anything.",
        )

    def handle(self, *args, **options):
        dry_run = bool(options.get("dry_run"))
        certificates = (
            Certificate.objects.filter(review_status__in=LEARNED_STATUSES)
            .select_related("document", "entity", "exam", "language")
            .order_by("pk")
        )
        totals = {
            "certificates": 0,
            "aliases": 0,
            "exams": 0,
            "equivalences": 0,
            "cefr_rules": 0,
            "conflicts": 0,
            "profiles": 0,
            "events": 0,
            "errors": 0,
        }
        for certificate in certificates:
            totals["certificates"] += 1
            try:
                outcome = self._learn_one(certificate, dry_run=dry_run)
            except Exception as exc:  # keep the backfill going per certificate
                totals["errors"] += 1
                self.stdout.write(self.style.WARNING(f"  certificate {certificate.pk}: {exc}"))
                continue
            totals["aliases"] += len(outcome["aliases_created"])
            totals["exams"] += len(outcome["exams_created"])
            totals["equivalences"] += len(outcome["equivalences_created"])
            totals["cefr_rules"] += len(outcome["cefr_rules_created"])
            totals["conflicts"] += len(outcome["conflicts"])
            if outcome.get("profile_updated"):
                totals["profiles"] += 1
            if outcome.get("event_created"):
                totals["events"] += 1

        prefix = "Dry-run" if dry_run else "Learned"
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}: {totals['certificates']} certificados, "
                f"{totals['aliases']} aliases, {totals['exams']} exams, "
                f"{totals['equivalences']} equivalencias, "
                f"{totals['cefr_rules']} reglas CEFR, "
                f"{totals['conflicts']} conflictos, "
                f"{totals['profiles']} perfiles, "
                f"{totals['events']} eventos, {totals['errors']} errores."
            )
        )

    def _learn_one(self, certificate: Certificate, *, dry_run: bool) -> dict:
        """Learn for one certificate inside a transaction.

        ``--dry-run`` rolls everything back after computing the outcome.
        """
        try:
            with transaction.atomic():
                outcome = learn_from_certificate(certificate, None)
                outcome["profile_updated"] = learn_format_profile(certificate) is not None
                outcome["event_created"] = False
                if not _outcome_is_empty(outcome):
                    ReviewEvent.objects.create(
                        certificate=certificate,
                        event_type=ReviewEvent.EventType.LEARN,
                        actor=None,
                        reason="Aprendizaje desde historial",
                        after={"learning": outcome},
                    )
                    outcome["event_created"] = True
                if dry_run:
                    raise _DryRun()
                return outcome
        except _DryRun:
            return outcome
