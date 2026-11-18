"""Evaluation metrics. Pure functions over per-case result dicts (see runner.py)."""
from __future__ import annotations

import unicodedata


def _norm(s: str) -> str:
    return unicodedata.normalize("NFC", s or "").lower().replace(",", "")


def facts_present(answer: str, facts: list[str]) -> bool:
    a = _norm(answer)
    return all(_norm(f) in a for f in facts)


def forbidden_present(answer: str, forbidden: list[str]) -> bool:
    a = _norm(answer)
    return any(_norm(f) in a for f in forbidden)


def _ratio(num: float, den: float):
    return round(num / den, 4) if den else None


def compute_metrics(results: list[dict]) -> dict:
    """
    results[i] keys: id, category, answerable(bool), answered(bool), answer, relevant_docs(list[str]),
      retrieved_docs(list[str]) (ordered, with repeats), expected_facts, forbidden, source_docs(list[str]),
      leaked(bool), faithful(bool|None)
    """
    answerable = [r for r in results if r["answerable"]]
    refusal_cases = [r for r in results if not r["answerable"]]

    # Retrieval quality (document level) over answerable cases with known relevant docs
    precs, recs, ctx_rel = [], [], []
    for r in answerable:
        rel = set(r.get("relevant_docs") or [])
        got = r.get("retrieved_docs") or []
        if not rel:
            continue
        hits = [d for d in got if d in rel]
        precs.append(len(hits) / len(got) if got else 0.0)
        recs.append(len(set(hits)) / len(rel))
        ctx_rel.append(len(hits) / len(got) if got else 0.0)

    correct = [r for r in answerable if r["answered"] and facts_present(r["answer"], r.get("expected_facts") or []) and not forbidden_present(r["answer"], r.get("forbidden") or [])]
    answered_cases = [r for r in results if r["answered"]]
    unsupported = [r for r in answered_cases if not r["answerable"]]  # answered although it must be refused
    cited_ok = [
        r for r in answered_cases
        if r["answerable"] and r.get("source_docs") and set(r["source_docs"]) <= set(r.get("relevant_docs") or r["source_docs"])
    ]
    predicted_refusals = [r for r in results if not r["answered"]]
    true_refusals = [r for r in predicted_refusals if not r["answerable"]]

    faithful_known = [r for r in answered_cases if r.get("faithful") is not None]
    return {
        "cases": len(results),
        "retrieval_precision_at_k": round(sum(precs) / len(precs), 4) if precs else None,
        "retrieval_recall_at_k": round(sum(recs) / len(recs), 4) if recs else None,
        "context_relevance": round(sum(ctx_rel) / len(ctx_rel), 4) if ctx_rel else None,
        "answer_correctness": _ratio(len(correct), len(answerable)),
        "answered_rate_on_answerable": _ratio(len([r for r in answerable if r["answered"]]), len(answerable)),
        "answer_faithfulness": _ratio(len([r for r in faithful_known if r["faithful"]]), len(faithful_known)),
        "citation_correctness": _ratio(len(cited_ok), len([r for r in answered_cases if r["answerable"]])),
        "unsupported_answer_rate": _ratio(len(unsupported), len(refusal_cases)),
        "refusal_precision": _ratio(len(true_refusals), len(predicted_refusals)),
        "refusal_recall": _ratio(len(true_refusals), len(refusal_cases)),
        "cross_tenant_leakage_rate": _ratio(len([r for r in results if r.get("leaked")]), len(results)),
    }


def by_category(results: list[dict]) -> dict:
    cats: dict[str, list[dict]] = {}
    for r in results:
        cats.setdefault(r.get("category", "uncategorised"), []).append(r)
    return {c: compute_metrics(rs) for c, rs in sorted(cats.items())}


def sweep_thresholds(cases: list[dict], thresholds: list[float]) -> list[dict]:
    """
    cases[i]: {answerable: bool, best_similarity: float}. Retrieval-only: predicts refusal when
    best_similarity < threshold. Reports refusal precision/recall and answerable coverage.
    """
    rows = []
    for t in thresholds:
        refused = [c for c in cases if c["best_similarity"] < t]
        should_refuse = [c for c in cases if not c["answerable"]]
        true_ref = [c for c in refused if not c["answerable"]]
        answerable = [c for c in cases if c["answerable"]]
        rows.append({
            "threshold": round(t, 3),
            "refusal_precision": _ratio(len(true_ref), len(refused)),
            "refusal_recall": _ratio(len(true_ref), len(should_refuse)),
            "answerable_coverage": _ratio(len([c for c in answerable if c["best_similarity"] >= t]), len(answerable)),
        })
    return rows


def recommend_threshold(rows: list[dict], min_refusal_recall: float = 0.98):
    ok = [r for r in rows if (r["refusal_recall"] or 0) >= min_refusal_recall]
    if not ok:
        return None
    return max(ok, key=lambda r: ((r["answerable_coverage"] or 0), -r["threshold"]))["threshold"]
