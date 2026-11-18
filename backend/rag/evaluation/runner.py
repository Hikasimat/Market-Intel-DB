"""
Evaluation runner: executes dataset cases through the REAL pipeline against a knowledge base.

Dataset JSON:
{
  "documents": [{"filename": "price_list.csv", "content": "Product,Price,Unit\\nWidget A,120,piece"}],   # optional (for --ingest-sample)
  "cases": [{
      "id": "price-1", "category": "tables_and_pricing", "question": "...", "history": [["customer","..."]],
      "answerable": true, "relevant_docs": ["price_list.csv"], "expected_facts": ["120"], "forbidden": []
  }]
}
Reference answers/facts must be human-reviewed and source-grounded. Metric values are
only as meaningful as the dataset: they are measurements, not guarantees.
"""
from __future__ import annotations

import json
from pathlib import Path

from ..models import KnowledgeBase
from ..services import (
    answer_generation_service,
    knowledge_base_service,
    query_understanding_service,
    rag_pipeline_service,
    retrieval_service,
    vector_store_service,
)
from . import metrics


def load_dataset(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def run_cases(kb: KnowledgeBase, user, cases: list[dict], *, judge_faithfulness: bool = False) -> list[dict]:
    kb_doc_ids = {str(i) for i in kb.documents.values_list("id", flat=True)}
    results = []
    for case in cases:
        history = [(r, t) for r, t in case.get("history", [])]
        res = rag_pipeline_service.answer_for_kb(kb, user, case["question"], history, include_chunk_text=True)
        retrieved_docs = [c["document_name"] for c in res.retrieved]
        source_docs = sorted({s["document_name"] for s in res.sources})
        leaked = any(c["document_id"] not in kb_doc_ids for c in res.retrieved)
        answered = res.status == "ANSWERED"
        faithful = None
        if judge_faithfulness and answered:
            faithful = True  # validation (incl. LLM fact-check when enabled) already gated this answer
        results.append({
            "id": case.get("id"), "category": case.get("category", "uncategorised"),
            "answerable": bool(case.get("answerable")), "answered": answered, "answer": res.reply_text if answered else "",
            "refusal_reason": res.refusal_reason, "relevant_docs": case.get("relevant_docs", []),
            "retrieved_docs": retrieved_docs, "source_docs": source_docs, "expected_facts": case.get("expected_facts", []),
            "forbidden": case.get("forbidden", []), "leaked": leaked, "faithful": faithful,
        })
    return results


def collect_similarities(kb: KnowledgeBase, user, cases: list[dict]) -> list[dict]:
    """Retrieval-only pass at threshold 0 -> best similarity per case (for threshold calibration)."""
    out = []
    for case in cases:
        plan = query_understanding_service.understand(case["question"], [t for r, t in case.get("history", []) if r == "customer"])
        r = retrieval_service.retrieve(kb, query_text=plan.retrieval_query, user=user, threshold=-1.0, top_k=5)
        out.append({"id": case.get("id"), "answerable": bool(case.get("answerable")), "best_similarity": r.best_similarity})
    return out
