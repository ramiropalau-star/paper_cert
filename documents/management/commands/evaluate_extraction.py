"""Management command for the offline extraction evaluation harness."""

from django.core.management.base import BaseCommand, CommandError

from documents.models import EvaluationRun
from documents.services.evaluation import (
    GOLDEN_SET_NAME,
    build_golden_set,
    create_evaluation_run,
    latest_golden_set,
    run_evaluation_with_baseline,
)


class Command(BaseCommand):
    help = "Build golden sets and run/compare offline extraction evaluations."

    def add_arguments(self, parser):
        sub = parser.add_subparsers(dest="action", required=True)

        build = sub.add_parser("build-set", help="Create a new golden-set version")
        build.add_argument("--set-name", default=GOLDEN_SET_NAME)

        run = sub.add_parser("run", help="Run a dry-run evaluation")
        run.add_argument("--set-name", default=GOLDEN_SET_NAME)
        run.add_argument("--version", type=int, default=None)
        run.add_argument("--entity", type=int, default=None)
        run.add_argument("--baseline", type=int, default=None)

        listing = sub.add_parser("list", help="List golden sets and runs")
        listing.add_argument("--set-name", default=GOLDEN_SET_NAME)

        show = sub.add_parser("show", help="Show one evaluation run")
        show.add_argument("run_id", type=int)

        compare = sub.add_parser("compare", help="Compare two evaluation runs")
        compare.add_argument("run_a", type=int)
        compare.add_argument("run_b", type=int)

    def handle(self, *args, **options):
        action = options["action"]
        if action == "build-set":
            result = build_golden_set(set_name=options["set_name"])
            self.stdout.write(
                f"Golden set '{result['set_name']}' v{result['set_version']}: "
                f"{result['cases']} cases ({result['skipped']} skipped)"
            )
        elif action == "run":
            baseline = None
            if options["baseline"] is not None:
                baseline = EvaluationRun.objects.filter(pk=options["baseline"]).first()
                if baseline is None:
                    raise CommandError(f"Baseline run {options['baseline']} not found")
            run = create_evaluation_run(
                set_name=options["set_name"],
                set_version=options["version"],
                entity_id=options["entity"],
                baseline_run=baseline,
            )
            self.stdout.write(f"Evaluation run {run.pk} started…")
            run_evaluation_with_baseline(run, baseline_run=baseline)
            run.refresh_from_db()
            self.stdout.write(f"Run {run.pk}: {run.status}")
            if run.error:
                self.stderr.write(run.error)
            metrics = run.metrics or {}
            overall = metrics.get("overall") or {}
            totals = overall.get("totals") or {}
            self.stdout.write(
                f"cases={metrics.get('case_count', 0)} "
                f"normalized_accuracy={totals.get('normalized_accuracy')} "
                f"missing_rate={totals.get('missing_rate')}"
            )
            if run.comparison:
                self.stdout.write(
                    f"vs baseline {run.baseline_run_id}: "
                    f"regressions={run.comparison.get('regressions')} "
                    f"improvements={run.comparison.get('improvements')}"
                )
        elif action == "list":
            latest = latest_golden_set(options["set_name"])
            self.stdout.write(f"Golden set '{options['set_name']}': {latest}")
            for run in EvaluationRun.objects.all()[:20]:
                self.stdout.write(
                    f"  run {run.pk}: {run.set_name} v{run.set_version} "
                    f"{run.status} {run.created_at:%Y-%m-%d %H:%M}"
                )
        elif action == "show":
            run = EvaluationRun.objects.filter(pk=options["run_id"]).first()
            if run is None:
                raise CommandError(f"Run {options['run_id']} not found")
            self.stdout.write(str(run.metrics))
            if run.comparison:
                self.stdout.write(str(run.comparison))
        elif action == "compare":
            from documents.services.evaluation import compare_metrics

            run_a = EvaluationRun.objects.filter(pk=options["run_a"]).first()
            run_b = EvaluationRun.objects.filter(pk=options["run_b"]).first()
            if run_a is None or run_b is None:
                raise CommandError("Both run ids must exist")
            self.stdout.write(str(compare_metrics(run_a.metrics or {}, run_b.metrics or {})))
