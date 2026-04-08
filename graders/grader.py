"""
Main grader that coordinates all three scoring components.

SCORING:
  total = 0.70 * functional + 0.20 * code_quality + 0.10 * visual

Performance budget: < 30 seconds total.

NOTE: This module is called from FastAPI sync handlers which run inside a
thread-pool executor (not the main thread).  Do NOT use signal.alarm /
signal.SIGALRM here — they only work on the main thread and will raise
  ValueError: signal only works in main thread
Playwright's own per-call timeouts (timeout= params on goto, click, fill,
wait_for_selector, etc.) are the correct mechanism for bounding flow time.
"""
from __future__ import annotations
from playwright.sync_api import Page

_HOME_URL = "http://127.0.0.1:8000"


def _run_flow(flow_fn, page: Page) -> tuple[bool, str]:
    """
    Run one Playwright flow, catching every exception.

    Individual Playwright calls inside the flow already carry explicit
    timeout= parameters, so infinite hangs are not possible without SIGALRM.
    """
    try:
        return flow_fn(page)
    except Exception as exc:
        return False, f"Flow crashed: {exc}"


def grade_submission(
    page: Page,
    workspace: str,
    framework: str,
    task_id: str,
    task: dict,
) -> dict:
    """
    Run all three graders and return a result dict.

    Keys: total_score, functional_score, code_quality_score, visual_score,
          flows_passing, flows_total, feedback
    """
    from tasks.task_definitions import TASKS
    from graders.visual import visual_heuristic_score, get_visual_details
    from graders.code_quality import compute_code_quality

    task_def = TASKS.get(task_id) or task
    flows = task_def.get("flows", [])

    # ── 1. Functional score (0.70 weight) ─────────────────────────────────
    functional_results: list[tuple[str, bool, str]] = []
    flows_passing = 0

    for flow_name, flow_fn in flows:
        ok, msg = _run_flow(flow_fn, page)
        functional_results.append((flow_name, ok, msg))
        if ok:
            flows_passing += 1

    flows_total = len(flows)
    functional_score = flows_passing / flows_total if flows_total > 0 else 0.0

    # ── 2. Code quality score (0.20 weight) ───────────────────────────────
    try:
        quality_result = compute_code_quality(workspace, framework)
        code_quality_score = quality_result.total_score
        quality_detail = quality_result.explanation
    except Exception as exc:
        code_quality_score = 0.5
        quality_detail = f"Quality check error: {exc}"

    # ── 3. Visual heuristic score (0.10 weight) ───────────────────────────
    try:
        page.goto(_HOME_URL, timeout=8000, wait_until="domcontentloaded")
        page.wait_for_timeout(500)
        visual_score = visual_heuristic_score(page)
        visual_detail = get_visual_details(page)
    except Exception as exc:
        visual_score = 0.5
        visual_detail = f"Visual check error: {exc}"

    # ── Final weighted score ───────────────────────────────────────────────
    total_score = round(
        min(1.0, max(0.0,
            0.70 * functional_score
            + 0.20 * code_quality_score
            + 0.10 * visual_score
        )),
        4,
    )

    # ── Human-readable feedback ────────────────────────────────────────────
    flow_lines = [
        f"  {'✓' if ok else '✗'} {name}: {msg}"
        for name, ok, msg in functional_results
    ]
    feedback = "\n".join([
        f"=== FINAL SCORE: {total_score:.3f} ===",
        "",
        f"Functional ({flows_passing}/{flows_total} flows): {functional_score:.3f}",
        *flow_lines,
        "",
        f"Code Quality: {code_quality_score:.3f}",
        f"  {quality_detail}",
        "",
        f"Visual: {visual_score:.3f}",
        f"  {visual_detail}",
        "",
        (
            f"Total = 0.70×{functional_score:.3f}"
            f" + 0.20×{code_quality_score:.3f}"
            f" + 0.10×{visual_score:.3f}"
            f" = {total_score:.3f}"
        ),
    ])

    return {
        "total_score": total_score,
        "functional_score": functional_score,
        "code_quality_score": code_quality_score,
        "visual_score": visual_score,
        "flows_passing": flows_passing,
        "flows_total": flows_total,
        "feedback": feedback,
    }
