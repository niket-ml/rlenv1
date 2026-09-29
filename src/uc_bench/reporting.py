# ruff: noqa: E501
"""Generate an honest, self-contained UC-Bench HTML report."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def _score_bar(label: str, value: float, tone: str = "blue") -> str:
    bounded = max(0.0, min(100.0, value))
    return (
        '<div class="bar-row"><span class="bar-label">'
        f"{html.escape(label)}</span><div class=\"bar-track\"><div class=\"bar {tone}\" "
        f'style="width:{bounded:.2f}%"></div></div><strong>{value:.1f}</strong></div>'
    )


def render_report(
    *,
    evaluation: dict[str, Any],
    reference_separation: dict[str, Any],
    variant_controls: dict[str, Any],
    runtime_smoke: dict[str, Any],
) -> str:
    ranking_available = bool(evaluation.get("model_ranking_available"))
    if ranking_available:
        status_label = "MODEL RESULTS AVAILABLE"
        status_class = "ready"
        status_detail = (
            f"{int(evaluation.get('valid_episode_rows', 0))} valid scored trajectories."
        )
    else:
        status_label = "PRE-RESULT — NO MODEL RANKING"
        status_class = "blocked"
        status_detail = html.escape(
            str(evaluation.get("reason", "Repeated model evaluation has not run."))
        )

    grading_bars = "".join(
        [
            _score_bar("Expert reference", float(reference_separation["expert"]["score"])),
            _score_bar("Mediocre decision", float(reference_separation["mediocre"]["score"]), "amber"),
            _score_bar(
                "Keyword-only caution",
                float(reference_separation["keyword_only_control"]["score"]),
                "amber",
            ),
            _score_bar(
                "Structured false-pass claims",
                float(reference_separation["structured_forgery_control"]["score"]),
                "amber",
            ),
            _score_bar(
                "Hard-invalid access",
                float(reference_separation["hard_invalidation_control"]["score"]),
                "red",
            ),
        ]
    )
    policy_bars = "".join(
        _score_bar(label.replace("_", " ").title(), float(value), "purple")
        for label, value in variant_controls["policy_control_scores"].items()
    )
    runtime_failures = int(runtime_smoke["fixture_infrastructure_failures"])
    real_smoke = bool(runtime_smoke["real_model_smoke_executed"])
    isolation_ready = bool(runtime_smoke.get("selected_isolation_ready", False))
    isolation_backend = html.escape(
        str(runtime_smoke.get("selected_isolation_backend") or "unconfigured")
    )
    positive = variant_controls["sufficient_evidence_positive_control"]

    leaderboard_rows = ""
    if ranking_available:
        for row in evaluation.get("group_summaries", []):
            interval = row["score_interval"]
            leaderboard_rows += (
                "<tr>"
                f"<td>{html.escape(str(row['model_id']))}</td>"
                f"<td>{html.escape(str(row['condition']))}</td>"
                f"<td>{float(row['score_mean']):.1f}</td>"
                f"<td>{float(interval[0]):.1f}–{float(interval[1]):.1f}</td>"
                f"<td>{float(row['contract_valid_rate']):.0%}</td>"
                f"<td>{int(row['n'])}</td>"
                "</tr>"
            )
    else:
        leaderboard_rows = (
            '<tr><td colspan="6" class="empty">No rows. Model endpoints and an isolated '
            "coding runtime must be configured before rankings are displayed.</td></tr>"
        )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>UC-Bench v0 report</title>
<style>
:root {{ --ink:#14213d; --muted:#5d687c; --line:#d9e0ea; --paper:#f5f7fb;
--blue:#1f6feb; --purple:#7657d5; --amber:#d78b16; --red:#c43d4b; --green:#18794e; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; color:var(--ink); background:var(--paper); font:15px/1.5 Inter,ui-sans-serif,system-ui,sans-serif; }}
main {{ width:min(1160px,calc(100% - 32px)); margin:32px auto 64px; }}
.hero {{ background:#101c36; color:white; padding:34px; border-radius:18px; box-shadow:0 16px 50px #14213d22; }}
.eyebrow {{ letter-spacing:.12em; text-transform:uppercase; font-size:12px; color:#9ebcff; }}
h1 {{ margin:5px 0 8px; font-size:42px; line-height:1.05; }}
.hero p {{ max-width:780px; color:#d7e2f8; margin:0; }}
.status {{ display:inline-block; margin-top:20px; padding:8px 12px; border-radius:999px; font-weight:750; font-size:12px; letter-spacing:.06em; }}
.status.blocked {{ background:#ffe4ad; color:#603c00; }} .status.ready {{ background:#b7f3d4; color:#074f31; }}
.grid {{ display:grid; grid-template-columns:repeat(12,1fr); gap:18px; margin-top:18px; }}
.card {{ background:white; border:1px solid var(--line); border-radius:16px; padding:22px; }}
.span-4 {{ grid-column:span 4; }} .span-6 {{ grid-column:span 6; }} .span-12 {{ grid-column:span 12; }}
h2 {{ margin:0 0 4px; font-size:20px; }} h3 {{ margin:18px 0 8px; }}
.sub {{ color:var(--muted); margin:0 0 18px; }}
.metric {{ font-size:34px; font-weight:780; letter-spacing:-.03em; }} .metric small {{ font-size:14px; color:var(--muted); font-weight:500; }}
.bar-row {{ display:grid; grid-template-columns:155px 1fr 38px; gap:10px; align-items:center; margin:10px 0; }}
.bar-label {{ color:#33405a; font-size:13px; }} .bar-track {{ height:11px; background:#edf1f7; border-radius:99px; overflow:hidden; }}
.bar {{ height:100%; border-radius:99px; background:var(--blue); }} .bar.amber {{ background:var(--amber); }} .bar.red {{ background:var(--red); }} .bar.purple {{ background:var(--purple); }}
table {{ width:100%; border-collapse:collapse; }} th,td {{ padding:11px 10px; text-align:left; border-bottom:1px solid var(--line); }}
th {{ color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.05em; }} .empty {{ color:var(--muted); text-align:center; padding:30px; }}
.flow {{ display:flex; align-items:center; gap:8px; flex-wrap:wrap; margin-top:18px; }}
.node {{ padding:10px 13px; border:1px solid #b8c5d9; border-radius:10px; background:#f8faff; font-weight:650; }} .arrow {{ color:#8491a7; }}
.tag {{ display:inline-block; border:1px solid var(--line); border-radius:99px; padding:3px 8px; margin:3px; font-size:12px; color:var(--muted); }}
.warning {{ border-left:4px solid var(--amber); background:#fff8e8; padding:13px 15px; margin-top:15px; }}
@media(max-width:800px) {{ .span-4,.span-6 {{ grid-column:span 12; }} h1 {{ font-size:34px; }} .bar-row {{ grid-template-columns:120px 1fr 34px; }} }}
</style>
</head>
<body><main>
<section class="hero">
  <div class="eyebrow">UC-Bench · v0 evidence report</div>
  <h1>Can an agent fail scientifically—and fail well?</h1>
  <p>One anti-TNF biomarker diligence chain. Irreversible commit. Private transfer validation. Evidence-backed diagnosis, containment, calibration, and recovery.</p>
  <div class="status {status_class}">{status_label}</div>
  <p style="margin-top:9px">{status_detail}</p>
</section>
<section class="grid">
  <article class="card span-4"><h2>Authentic transfer</h2><p class="sub">GSE92415, never a headline rank metric</p><div class="metric">0.667 <small>AUC</small></div><p>95% bootstrap interval 0.513–0.814 · n=59 · decision: <strong>insufficient evidence</strong>.</p></article>
  <article class="card span-4"><h2>Positive decision control</h2><p class="sub">Synthetic; never a biology claim</p><div class="metric">{float(positive['auc']):.3f} <small>AUC</small></div><p>n={int(positive['evaluated_n'])}; threshold clearly met so abstention loses.</p></article>
  <article class="card span-4"><h2>Runtime readiness</h2><p class="sub">Fixtures are not model results</p><div class="metric">{runtime_failures} <small>fixture infra failures</small></div><p>Isolation: <strong>{isolation_backend}</strong> · ready: <strong>{str(isolation_ready).lower()}</strong>.<br>Real model smoke executed: <strong>{str(real_smoke).lower()}</strong>.</p></article>
  <article class="card span-12"><h2>Agent decision chain</h2><p class="sub">The predictor is an artifact; the evaluated object is the trajectory.</p><div class="flow"><span class="node">Audit supplied data</span><span class="arrow">→</span><span class="node">Build inspectable model</span><span class="arrow">→</span><span class="node">Commit hashes + expected AUC</span><span class="arrow">→</span><span class="node">Private aggregate reveal</span><span class="arrow">→</span><span class="node">Advance / stop / insufficient</span></div></article>
  <article class="card span-6"><h2>Grader separation</h2><p class="sub">Model/data claims are independently recomputed; no prose matching.</p>{grading_bars}</article>
  <article class="card span-6"><h2>Symmetric policy controls</h2><p class="sub">Universal policies must remain below 60.</p>{policy_bars}</article>
  <article class="card span-12"><h2>Model leaderboard</h2><p class="sub">Display the complete model + harness + runtime tuple, with clustered uncertainty.</p><table><thead><tr><th>Model/harness</th><th>Condition</th><th>Score</th><th>95% interval</th><th>Contract valid</th><th>n</th></tr></thead><tbody>{leaderboard_rows}</tbody></table><div class="warning"><strong>No fabricated rows.</strong> This table stays empty until repeated real-model trajectories pass the audit.</div></article>
  <article class="card span-12"><h2>Failure atlas surfaces</h2><p class="sub">What the release will make inspectable after real rollouts.</p><span class="tag">endpoint mismatch</span><span class="tag">platform shortcut</span><span class="tag">post-reveal mutation</span><span class="tag">overconfident expected AUC</span><span class="tag">generic abstention</span><span class="tag">sample identity conflict</span><span class="tag">feature dropout</span><span class="tag">data-withheld retention</span><p>Each claim must link to a trajectory event and a grader-observed artifact. Authentic biology and controlled failure variants remain separate.</p></article>
</section>
</main></body></html>"""
