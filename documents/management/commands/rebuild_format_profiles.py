"""Rebuild format profiles from their current approved samples.

Every rebuild bumps ``version`` and preserves the previous state in
``version_history`` for audit. Profiles whose cohort no longer has enough
approved samples are deactivated rather than deleted.
"""

from django.core.management.base import BaseCommand

from catalog.models import FormatProfile
from documents.services.format_profile import rebuild_profile


class Command(BaseCommand):
    help = "Rebuild all active format profiles, preserving version history."

    def add_arguments(self, parser):
        parser.add_argument("--entity", type=int, default=None, help="Only this entity id")
        parser.add_argument("--inactive", action="store_true", help="Include inactive profiles")

    def handle(self, *args, **options):
        qs = FormatProfile.objects.select_related("entity", "exam").order_by("entity__name", "year")
        if options["entity"] is not None:
            qs = qs.filter(entity_id=options["entity"])
        if not options["inactive"]:
            qs = qs.filter(is_active=True)

        rebuilt = skipped = 0
        for profile in qs:
            result = rebuild_profile(profile)
            if result is None:
                profile.is_active = False
                profile.save(update_fields=["is_active", "updated_at"])
                self.stdout.write(
                    self.style.WARNING(f"deactivated {profile} (no approved samples left)")
                )
                skipped += 1
            else:
                rebuilt += 1
                self.stdout.write(
                    f"rebuilt {result} -> v{result.version} "
                    f"(samples={result.sample_count}, drift={result.drift_detected})"
                )
        self.stdout.write(self.style.SUCCESS(f"rebuilt={rebuilt} deactivated={skipped}"))
