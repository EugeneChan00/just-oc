"""
autoresearch.harness.scorer

Scoring hierarchy:
  sub_metric (bool) → metric (mean of 3) → category (mean of 3) → composite (mean of 3)
  Run score = mean of N composite scores across N prompts.
"""

from autoresearch.harness.spec_reader import CATEGORIES, METRIC_ORDER, SUB_METRIC_ORDER, CATEGORY_IDS


def score_sub_metrics(eval_result: dict[str, dict]) -> dict[str, float | None]:
    """Convert {numeric_id: {description, result}} to {numeric_id: 0.0 or 1.0 or None}."""
    return {
        nid: (1.0 if v["result"] is True else 0.0 if v["result"] is False else None)
        for nid, v in eval_result.items()
        if "." in nid
    }


def score_metric(scores: dict[str, float | None], category: str, metric: str) -> float | None:
    """Mean of 3 sub-metric scores for one metric. None if all sub-metrics are None."""
    cat_id = CATEGORY_IDS[category]
    met_idx = METRIC_ORDER[category].index(metric) + 1
    sub_scores = []
    for sub_idx in range(1, 4):
        nid = f"{cat_id}.{met_idx}.{sub_idx}"
        val = scores.get(nid)
        if val is not None:
            sub_scores.append(val)
    return sum(sub_scores) / len(sub_scores) if sub_scores else None


def score_category(scores: dict[str, float | None], category: str) -> float | None:
    """Mean of 3 metric scores for one category. None if all metrics are None."""
    metric_scores = []
    for metric in METRIC_ORDER[category]:
        ms = score_metric(scores, category, metric)
        if ms is not None:
            metric_scores.append(ms)
    return sum(metric_scores) / len(metric_scores) if metric_scores else None


def score_composite(scores: dict[str, float | None]) -> float:
    """Mean of 3 category scores. Returns 0.0 if all None."""
    cat_scores = []
    for cat in CATEGORIES:
        cs = score_category(scores, cat)
        if cs is not None:
            cat_scores.append(cs)
    return sum(cat_scores) / len(cat_scores) if cat_scores else 0.0


def score_run(prompt_composites: list[float]) -> float:
    """Mean of N composite scores across N prompts."""
    return sum(prompt_composites) / len(prompt_composites) if prompt_composites else 0.0


def full_breakdown(eval_result: dict[str, dict]) -> dict:
    """Compute full scoring breakdown from a 27-field eval result.

    Returns:
        {
            "sub_metrics": {nid: 0.0/1.0/None, ...},
            "metrics": {metric_name: float, ...},
            "categories": {category_name: float, ...},
            "composite": float,
        }
    """
    sub_scores = score_sub_metrics(eval_result)

    metrics = {}
    for cat in CATEGORIES:
        for metric in METRIC_ORDER[cat]:
            ms = score_metric(sub_scores, cat, metric)
            metrics[metric] = ms

    categories = {}
    for cat in CATEGORIES:
        categories[cat] = score_category(sub_scores, cat)

    composite = score_composite(sub_scores)

    return {
        "sub_metrics": sub_scores,
        "metrics": metrics,
        "categories": categories,
        "composite": composite,
    }


def format_score_summary(breakdown: dict) -> str:
    """Human-readable score summary for optimizer context."""
    lines = []
    lines.append(f"Composite: {breakdown['composite']:.3f}")
    for cat in CATEGORIES:
        cs = breakdown["categories"].get(cat)
        lines.append(f"  {cat}: {cs:.3f}" if cs is not None else f"  {cat}: N/A")
        for metric in METRIC_ORDER[cat]:
            ms = breakdown["metrics"].get(metric)
            lines.append(f"    {metric}: {ms:.3f}" if ms is not None else f"    {metric}: N/A")
    return "\n".join(lines)
