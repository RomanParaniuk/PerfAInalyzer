"""Report renderer: render both Jinja2 templates from one `Report` instance and write
`perf-report.md` / `perf-report.html` to the output directory, overwriting any prior
run's files (FR-017, stateless across runs).

Both renderings share one context and one set of formatting helpers, so their content
is identical by construction (Principle IV); output is always English regardless of the
system locale (FR-018) because every user-facing string lives in the templates."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, PackageLoader

from src.models.action_item import ActionItem
from src.models.finding import Finding, LocationRef
from src.models.report import AnalysisRun, Report, RunStatus
from src.models.stage import STAGE_LABELS, StageName

MD_TEMPLATE = "perf-report.md.j2"
HTML_TEMPLATE = "perf-report.html.j2"

RUN_STATUS_TEXT: dict[RunStatus, str] = {
    RunStatus.IN_PROGRESS: "in progress",
    RunStatus.COMPLETED: "completed",
    RunStatus.COMPLETED_WITH_PARTIAL_RESULTS: "completed with partial results",
}


def location_str(location: LocationRef) -> str:
    text = location.file_path
    if location.line_start is not None:
        text += f":{location.line_start}"
        if location.line_end is not None and location.line_end != location.line_start:
            text += f"-{location.line_end}"
    if location.symbol:
        text += f" ({location.symbol})"
    return text


def stage_label(stage: StageName) -> str:
    return STAGE_LABELS[stage]


def _build_env() -> Environment:
    env = Environment(
        loader=PackageLoader("src.report", "templates"),
        autoescape=lambda name: name is not None and name.endswith(".html.j2"),
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    env.globals["location_str"] = location_str
    env.globals["stage_label"] = stage_label
    return env


_ENV = _build_env()


def render_report(report: Report, run: AnalysisRun) -> tuple[str, str]:
    """Render (markdown, html) from one shared context — content-equivalent by design."""
    findings_by_id: dict[str, Finding] = {
        f.finding_id: f for f in [*report.issues, *report.valuable_findings]
    }

    def action_item_stage(item: ActionItem) -> str:
        labels = []
        for fid in item.related_finding_ids:
            finding = findings_by_id.get(fid)
            if finding is not None:
                label = stage_label(finding.originating_stage)
                if label not in labels:
                    labels.append(label)
        return ", ".join(labels) if labels else "unknown"

    context = {
        "report": report,
        "scope_path": run.code_scope_path,
        "generated_at": report.generated_at.strftime("%Y-%m-%d %H:%M UTC"),
        "run_status": RUN_STATUS_TEXT[run.status],
        "languages": ", ".join(run.detected_languages) if run.detected_languages else "none detected",
        "action_item_stage": action_item_stage,
    }
    markdown = _ENV.get_template(MD_TEMPLATE).render(context)
    html = _ENV.get_template(HTML_TEMPLATE).render(context)
    return markdown, html


def write_reports(report: Report, run: AnalysisRun, output_dir: Path) -> tuple[Path, Path]:
    """Write both report files, overwriting previous runs' output (no history kept)."""
    output_dir.mkdir(parents=True, exist_ok=True)
    markdown, html = render_report(report, run)
    md_path = output_dir / "perf-report.md"
    html_path = output_dir / "perf-report.html"
    md_path.write_text(markdown, encoding="utf-8")
    html_path.write_text(html, encoding="utf-8")
    return md_path, html_path
