"""Run the evaluation framework against a knowledge base and print accuracy/refusal/leakage metrics."""
import json
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import BaseCommand, CommandError

from rag import conf
from rag.evaluation import metrics, runner
from rag.models import KnowledgeBase


class Command(BaseCommand):
    help = (
        "Evaluate RAG on a dataset. Use --kb <uuid> for an existing KB (documents already ingested), or "
        "--ingest-sample to build a temporary KB from the dataset's documents (deleted afterwards)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--dataset", required=True)
        parser.add_argument("--user", required=True, help="Username acting as the KB owner/tester.")
        parser.add_argument("--kb", help="Existing knowledge base UUID.")
        parser.add_argument("--ingest-sample", action="store_true")
        parser.add_argument("--sweep", action="store_true", help="Also run the relevance-threshold sweep.")
        parser.add_argument("--json", dest="json_out", help="Write full results to this path.")

    def handle(self, *args, **opts):
        user = get_user_model().objects.filter(username=opts["user"]).first()
        if user is None:
            raise CommandError("Unknown user.")
        data = runner.load_dataset(opts["dataset"])
        temp_kb = None
        try:
            if opts["ingest_sample"]:
                temp_kb = self._build_temp_kb(user, data)
                kb = temp_kb
            elif opts["kb"]:
                kb = KnowledgeBase.objects.get(pk=opts["kb"])
            else:
                raise CommandError("Provide --kb or --ingest-sample.")

            results = runner.run_cases(kb, user, data["cases"])
            overall = metrics.compute_metrics(results)
            self.stdout.write(json.dumps({"overall": overall, "by_category": metrics.by_category(results)}, indent=2))
            if opts["sweep"]:
                sims = runner.collect_similarities(kb, user, data["cases"])
                rows = metrics.sweep_thresholds(sims, [round(x * 0.05, 2) for x in range(2, 15)])
                self.stdout.write(json.dumps({"threshold_sweep": rows, "recommended_threshold": metrics.recommend_threshold(rows)}, indent=2))
            if opts["json_out"]:
                with open(opts["json_out"], "w", encoding="utf-8") as fh:
                    json.dump({"overall": overall, "results": results}, fh, ensure_ascii=False, indent=2)
            self.stdout.write(f"(current threshold={conf.min_relevance_threshold()}, top_k={conf.default_top_k()})")
        finally:
            if temp_kb is not None:
                from rag.services import knowledge_base_service

                knowledge_base_service.delete_knowledge_base(temp_kb, actor=user)

    def _build_temp_kb(self, user, data):
        from rag.services import document_upload_service
        from rag.workers.ingestion_worker import process_document

        kb = KnowledgeBase.objects.create(owner=user, name=f"__rag_eval_{tempfile.mktemp(prefix='')[-8:]}")
        for d in data.get("documents", []):
            doc = document_upload_service.upload_document(
                kb, user, SimpleUploadedFile(d["filename"], d["content"].encode("utf-8"), content_type="text/plain")
            )
            res = process_document(doc.pk)  # synchronous ingestion
            if res.status != "ready":
                raise CommandError(f"Ingestion of {d['filename']} failed: {res.message}")
        return kb
