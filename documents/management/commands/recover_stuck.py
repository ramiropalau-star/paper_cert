from django.core.management.base import BaseCommand

from documents.services.recovery import recover_stuck


class Command(BaseCommand):
    help = (
        "Recover documents and report jobs stuck in intermediate states. "
        "Use --dry-run to list stale work without changing anything."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="List stale documents and report jobs without modifying state.",
        )
        parser.add_argument(
            "--older-than",
            type=float,
            default=None,
            metavar="SECONDS",
            help="Only recover items unchanged for at least SECONDS (default: APP_RECOVERY_STALE_SECONDS).",
        )
        parser.add_argument(
            "--max-attempts",
            type=int,
            default=None,
            metavar="N",
            help="Recovery attempts before marking items as error (default: APP_RECOVERY_MAX_ATTEMPTS).",
        )
        parser.add_argument(
            "--documents-only",
            action="store_true",
            help="Only scan documents.",
        )
        parser.add_argument(
            "--reports-only",
            action="store_true",
            help="Only scan report jobs.",
        )

    def handle(self, *args, **options):
        report = recover_stuck(
            older_than_seconds=options["older_than"],
            max_attempts=options["max_attempts"],
            documents_only=options["documents_only"],
            reports_only=options["reports_only"],
            dry_run=options["dry_run"],
        )

        def _line(prefix, item):
            self.stdout.write(
                f"{prefix} #{item.pk} state={item.state} "
                f"age={item.age_seconds:.0f}s attempts={item.attempts}"
            )

        for item in report.stale_documents:
            _line("document", item)
        for item in report.stale_reports:
            _line("report", item)

        if options["dry_run"]:
            self.stdout.write(
                self.style.WARNING(
                    f"DRY RUN: {len(report.stale_documents)} stale document(s), "
                    f"{len(report.stale_reports)} stale report job(s). "
                    "No state was modified."
                )
            )
            return

        self.stdout.write(
            self.style.SUCCESS(
                f"Recovered: {report.requeued_documents} document(s) requeued, "
                f"{report.failed_documents} failed, "
                f"{report.retried_reports} report job(s) retried, "
                f"{report.failed_reports} failed."
            )
        )
