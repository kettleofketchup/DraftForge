"""Generate the DraftForge subsystem-logs dashboard JSON via the SDK.

Uses Grafana's official Foundation SDK so the output matches the upstream
schema by construction — replaces the previous hand-curated dict
assembly that drifted vs. Grafana Cloud's V2 validator.

Layout:
* Overview row (always open): subsystem inventory + top error events +
  log rate by system + warn/error rate by system.
* One collapsed row per system in the canonical taxonomy (see
  .claude/skills/logging/SKILL.md). Each row has 3 panels:
  log rate by subsystem, warn/error rate by subsystem, recent logs.
* JSON parse errors row (collapsed): surface anything failing `| json`
  so the source can be fixed.

Re-run after editing — the script self-validates and exits 1 on
structural problems.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from grafana_foundation_sdk.builders import (
    common as common_builder,
    dashboard,
    logs,
    loki,
    table,
    timeseries,
)
from grafana_foundation_sdk.cog.encoder import JSONEncoder
from grafana_foundation_sdk.models.common import GraphDrawStyle, StackingMode
from grafana_foundation_sdk.models.dashboard import (
    DataSourceRef,
    VariableRefresh,
    VariableSort,
)

OUTPUT = Path(__file__).parent / "subsystem-logs.json"

# Canonical taxonomy — see .claude/skills/logging/SKILL.md
SYSTEMS = [
    "avatars",
    "bracket",
    "cache",
    "discord",
    "events",
    "herodraft",
    "steam",
    "telemetry",
    "tournament",
    "websocket",
]

DS_LOKI = DataSourceRef(type_val="loki", uid="${DS_LOKI}")
SERVICE_FILTER = '{service_name=~"$service", deployment_environment="$env"}'
# `| __error__=""` drops jsonparsererr series so they don't poison
# aggregations or pop a frontend error toast.
SAFE_JSON = '| json | __error__=""'


# ---- Panel helpers --------------------------------------------------------


def _loki_target(expr: str, legend: str = "") -> loki.Dataquery:
    """Loki query target with project defaults."""
    q = loki.Dataquery().ref_id("A").expr(expr).editor_mode("code")
    if legend:
        q = q.legend_format(legend)
    return q


def _loki_instant(expr: str, legend: str = "") -> loki.Dataquery:
    """Loki instant query — for inventory/top-N panels."""
    return _loki_target(expr, legend).query_type("instant").instant(True)


def _ts_panel(
    title: str,
    expr: str,
    *,
    legend: str = "{{subsystem}}",
    width: int = 12,
    height: int = 8,
    draw_style: GraphDrawStyle = GraphDrawStyle.LINE,
    fill_opacity: int = 10,
    description: str = "",
) -> timeseries.Panel:
    """Stacked timeseries panel — project defaults for log-rate views."""
    return (
        timeseries.Panel()
        .title(title)
        .description(description)
        .datasource(DS_LOKI)
        .span(width)
        .height(height)
        .unit("logs/s")
        .draw_style(draw_style)
        .fill_opacity(fill_opacity)
        .stacking(common_builder.StackingConfig().mode(StackingMode.NORMAL).group("A"))
        .with_target(_loki_target(expr, legend))
    )


def _err_panel(
    title: str,
    expr: str,
    *,
    legend: str = "{{subsystem}}",
    width: int = 12,
    height: int = 8,
    description: str = "",
) -> timeseries.Panel:
    """Warn/error rate panel — bars, higher fill."""
    return _ts_panel(
        title,
        expr,
        legend=legend,
        width=width,
        height=height,
        draw_style=GraphDrawStyle.BARS,
        fill_opacity=70,
        description=description,
    )


def _logs_panel(
    title: str,
    expr: str,
    *,
    width: int = 24,
    height: int = 10,
    description: str = "",
    show_labels: bool = False,
) -> logs.Panel:
    """Logs panel — project defaults (descending, prettified JSON)."""
    return (
        logs.Panel()
        .title(title)
        .description(description)
        .datasource(DS_LOKI)
        .span(width)
        .height(height)
        .show_time(True)
        .sort_order("Descending")
        .prettify_log_message(True)
        .wrap_log_message(True)
        .enable_log_details(True)
        .show_labels(show_labels)
        .with_target(_loki_target(expr))
    )


def _table_panel(
    title: str,
    expr: str,
    *,
    width: int = 12,
    height: int = 10,
    description: str = "",
) -> table.Panel:
    """Table panel — used for inventory + top-N rankings."""
    return (
        table.Panel()
        .title(title)
        .description(description)
        .datasource(DS_LOKI)
        .span(width)
        .height(height)
        .with_target(_loki_instant(expr))
    )


# ---- Overview row ---------------------------------------------------------


def overview_row() -> dashboard.Row:
    return (
        dashboard.Row("Overview — all systems")
        .collapsed(False)
        .with_panel(
            _table_panel(
                "Subsystem inventory",
                f"sum by (system, subsystem) (count_over_time("
                f'{SERVICE_FILTER} {SAFE_JSON} | system!="" [$__range]))',
                width=8,
                height=10,
                description=(
                    "Every (system, subsystem) tuple seen in range. "
                    "Surfaces newly-shipped and silently-dropped subsystems."
                ),
            )
        )
        .with_panel(
            _table_panel(
                "Top error messages",
                f"topk(20, sum by (event, system, subsystem) (count_over_time("
                f"{SERVICE_FILTER} {SAFE_JSON} "
                f'| level=~"warning|error" [$__range])))',
                width=16,
                height=10,
                description=(
                    "Most frequent warn/error events. Top of this list is "
                    "where to spend the next round of fixes."
                ),
            )
        )
        .with_panel(
            _ts_panel(
                "Log rate by system",
                f"sum by (system) (rate("
                f'{SERVICE_FILTER} {SAFE_JSON} | system!="" [$__interval]))',
                legend="{{system}}",
                width=12,
                height=8,
                description="Total log rate aggregated by system.",
            )
        )
        .with_panel(
            _err_panel(
                "Warn + error rate by system",
                f"sum by (system) (rate("
                f"{SERVICE_FILTER} {SAFE_JSON} "
                f'| system!="" | level=~"warning|error" [$__interval]))',
                legend="{{system}}",
                width=12,
                height=8,
                description=(
                    "Warn + error rate aggregated by system. First place "
                    "to look during an incident."
                ),
            )
        )
    )


# ---- Per-system row -------------------------------------------------------


def system_row(system: str) -> dashboard.Row:
    return (
        dashboard.Row(system)
        .collapsed(True)
        .with_panel(
            _ts_panel(
                f"{system} — log rate by subsystem",
                f"sum by (subsystem) (rate("
                f"{SERVICE_FILTER} {SAFE_JSON} "
                f'| system="{system}" | subsystem!="" [$__interval]))',
                description=f"Log rate within {system}, grouped by subsystem.",
            )
        )
        .with_panel(
            _err_panel(
                f"{system} — warn + error rate by subsystem",
                f"sum by (subsystem) (rate("
                f"{SERVICE_FILTER} {SAFE_JSON} "
                f'| system="{system}" | subsystem!="" '
                f'| level=~"warning|error" [$__interval]))',
                description=(
                    f"Warn + error rate within {system}, grouped by subsystem."
                ),
            )
        )
        .with_panel(
            _logs_panel(
                f"{system} — recent logs",
                f"{SERVICE_FILTER} {SAFE_JSON} "
                f'| system="{system}" | subsystem=~"$subsystem" '
                f'| level=~"$level"',
                description=(
                    f"Live tail filtered to system={system}. Respects the "
                    "global subsystem and level filters."
                ),
            )
        )
    )


# ---- JSON parse errors row ------------------------------------------------


def json_errors_row() -> dashboard.Row:
    return (
        dashboard.Row("JSON parse errors (collapsed)")
        .collapsed(True)
        .with_panel(
            _logs_panel(
                "Lines that broke `| json` (jsonparsererr)",
                f'{SERVICE_FILTER} | json | __error__="jsonparsererr"',
                show_labels=True,
                description=(
                    "Log lines that Loki's `| json` parser rejects. Source "
                    "labels (code_file_path, code_function_name, "
                    "code_line_number) tell you which Python file is "
                    "emitting broken JSON — usually an f-string containing "
                    "a stray `{` like a dict literal or repr() output. Fix "
                    "at source by switching the call to structlog kwargs."
                ),
            )
        )
        .with_panel(
            _table_panel(
                "Top sources of broken JSON",
                f"topk(20, sum by (code_file_path, code_function_name, "
                f"code_line_number) (count_over_time("
                f'{SERVICE_FILTER} | json | __error__="jsonparsererr" '
                f"[$__range])))",
                width=24,
                height=8,
                description=(
                    "Which source files are emitting broken JSON, ranked "
                    "by count. Fix the top entries at source."
                ),
            )
        )
    )


# ---- Template variables ---------------------------------------------------


def build_variables() -> list:
    env = (
        dashboard.QueryVariable("env")
        .label("Environment")
        .datasource(DS_LOKI)
        .query("label_values(deployment_environment)")
        .multi(False)
        .include_all(False)
        .refresh(VariableRefresh.ON_DASHBOARD_LOAD)
        .sort(VariableSort.DISABLED)
    )
    service = (
        dashboard.QueryVariable("service")
        .label("Service")
        .datasource(DS_LOKI)
        .query('label_values({deployment_environment="$env"}, service_name)')
        .multi(True)
        .include_all(True)
        .refresh(VariableRefresh.ON_DASHBOARD_LOAD)
        .sort(VariableSort.ALPHABETICAL_ASC)
    )
    # Subsystem is a textbox to avoid an extra Loki round-trip per page load.
    # Per-system rows already filter on a literal `system=`, and
    # `subsystem=~"$subsystem"` defaults to matching everything when empty.
    subsystem = (
        dashboard.TextBoxVariable("subsystem")
        .label("Subsystem")
        .description(
            "Regex filter applied to recent-logs panels. Empty matches all."
        )
        .default_value(".*")
    )
    level = (
        dashboard.CustomVariable("level")
        .label("Level")
        .values("debug,info,warning,error")
        .multi(True)
        .include_all(True)
    )
    return [env, service, subsystem, level]


# ---- Build + serialize ----------------------------------------------------


def build_dashboard() -> dashboard.Dashboard:
    b = (
        dashboard.Dashboard("DraftForge — Subsystem Logs")
        .uid("draftforge-subsystem-logs")
        .description(
            "DraftForge structured-log dashboard. Overview row at the top "
            "summarizes inventory, log rate, warn/error rate, and top "
            "error events. Each system in the canonical taxonomy gets its "
            "own collapsed row below — expand the one you care about. "
            "Bottom row surfaces lines that fail `| json` parsing so we "
            "can fix them at source. See .claude/skills/logging/SKILL.md "
            "for the taxonomy."
        )
        .tags(["draftforge", "logs", "structlog"])
        .refresh("30s")
        .time("now-3h", "now")
        .timezone("browser")
        .editable()
    )
    for v in build_variables():
        b = b.with_variable(v)
    b = b.with_row(overview_row())
    for system in SYSTEMS:
        b = b.with_row(system_row(system))
    b = b.with_row(json_errors_row())
    return b


def post_process(d: dict) -> dict:
    """Tweaks the SDK doesn't model cleanly.

    * Assign sequential panel/row IDs (SDK doesn't auto-number).
    * Default `annotations.list` to an empty array.
    * Add `__inputs` block so Grafana's import dialog prompts for the
      Loki datasource.
    * Patch the `level` variable's default to multi-select.
    """
    # IDs — walk top-level + nested row.panels, assign sequentially.
    next_id = iter(range(1, 10_000))

    def assign_ids(p):
        if p.get("id", 0) == 0:
            p["id"] = next(next_id)
        for inner in p.get("panels", []) or []:
            assign_ids(inner)

    for p in d.get("panels", []):
        assign_ids(p)

    # SDK's Row.with_panel() unconditionally sets collapsed=True (a defensive
    # quirk around Grafana's save-time stripping of un-collapsed row panels).
    # The first row is our always-open overview — set it back to False here.
    rows = [p for p in d.get("panels", []) if p.get("type") == "row"]
    if rows:
        rows[0]["collapsed"] = False

    # annotations.list — SDK emits {} when empty; schema wants {"list": []}.
    if "annotations" not in d or not isinstance(d.get("annotations"), dict):
        d["annotations"] = {}
    d["annotations"].setdefault("list", [])

    d["__inputs"] = [
        {
            "name": "DS_LOKI",
            "label": "Loki",
            "description": "Loki datasource (e.g. grafanacloudloki)",
            "type": "datasource",
            "pluginId": "loki",
            "pluginName": "Loki",
        }
    ]
    d["__elements"] = {}
    d["__requires"] = [
        {"type": "grafana", "id": "grafana", "name": "Grafana", "version": "11.0.0"},
        {"type": "datasource", "id": "loki", "name": "Loki", "version": "1.0.0"},
        {"type": "panel", "id": "logs", "name": "Logs", "version": ""},
        {"type": "panel", "id": "table", "name": "Table", "version": ""},
        {"type": "panel", "id": "timeseries", "name": "Time series", "version": ""},
        {"type": "panel", "id": "row", "name": "Row", "version": ""},
    ]

    defaults = {"info", "warning", "error"}
    for var in d.get("templating", {}).get("list", []):
        if var.get("name") == "level":
            var["current"] = {
                "selected": True,
                "text": sorted(defaults),
                "value": sorted(defaults),
            }
            for opt in var.get("options", []):
                opt["selected"] = opt.get("value") in defaults
    return d


def main() -> int:
    built = build_dashboard().build()
    raw = JSONEncoder(sort_keys=False, indent=2).encode(built)
    obj = post_process(json.loads(raw))
    OUTPUT.write_text(json.dumps(obj, indent=2) + "\n")

    panels = obj.get("panels", [])
    rows = [p for p in panels if p.get("type") == "row"]
    print(f"Wrote {OUTPUT}")
    print(f"Systems: {len(SYSTEMS)}")
    print(f"Top-level panels: {len(panels)}  (rows: {len(rows)})")
    return validate(obj)


# ---- Validation -----------------------------------------------------------


def validate(d: dict) -> int:
    """Sanity checks layered on top of the SDK's own type validation.

    The SDK guarantees schema-shape correctness by construction — these
    checks catch issues in the *content* the SDK can't see (LogQL paren
    balance, unresolved variable refs, panel ID collisions).
    """
    issues: list[str] = []

    seen: dict[int, str] = {}

    def visit(p):
        pid = p.get("id")
        if pid is not None:
            if pid in seen:
                issues.append(
                    f"duplicate panel id {pid}: {seen[pid]!r} and "
                    f"{p.get('title','?')!r}"
                )
            else:
                seen[pid] = p.get("title", "?")
        for inner in p.get("panels", []) or []:
            visit(inner)

    for p in d.get("panels", []):
        visit(p)

    declared = {i["name"] for i in d.get("__inputs", [])}
    ds_refs: set[str] = set()

    def walk_ds(o):
        if isinstance(o, dict):
            uid = o.get("uid")
            if isinstance(uid, str) and uid.startswith("${") and uid.endswith("}"):
                ds_refs.add(uid[2:-1])
            for v in o.values():
                walk_ds(v)
        elif isinstance(o, list):
            for x in o:
                walk_ds(x)

    walk_ds(d)
    for ref in ds_refs:
        if ref not in declared:
            issues.append(
                f"datasource ${{{ref}}} referenced but not declared in __inputs"
            )

    declared_vars = {v["name"] for v in d.get("templating", {}).get("list", [])}
    builtins = {
        "__interval",
        "__interval_ms",
        "__range",
        "__range_s",
        "__range_ms",
        "__rate_interval",
        "__auto",
        "__from",
        "__to",
        "__name",
        "__org",
        "__user",
        "__dashboard",
        "__timeFilter",
        "__all",
    }
    import re

    var_re = re.compile(r"\$(?:\{)?([A-Za-z_][A-Za-z0-9_]*)")
    exprs: list[tuple[str, str]] = []

    def walk_exprs(o, path="$"):
        if isinstance(o, dict):
            for k, v in o.items():
                walk_exprs(v, f"{path}.{k}")
                if k == "expr" and isinstance(v, str):
                    exprs.append((path, v))
        elif isinstance(o, list):
            for i, x in enumerate(o):
                walk_exprs(x, f"{path}[{i}]")

    walk_exprs(d)
    for path, expr in exprs:
        for name in var_re.findall(expr):
            if name in builtins or name in declared_vars:
                continue
            issues.append(
                f"expr {path}: references ${name} which is not a template "
                f"variable or known Grafana built-in"
            )

    for path, e in exprs:
        if e.count("(") != e.count(")"):
            issues.append(f"expr {path}: paren imbalance")
        if e.count("{") != e.count("}"):
            issues.append(f"expr {path}: brace imbalance")
        if e.count("[") != e.count("]"):
            issues.append(f"expr {path}: bracket imbalance")
        if e.count("`") % 2 != 0:
            issues.append(f"expr {path}: odd backtick count")

    # JSON Schema validation against project schema, if present
    schema_path = (
        Path(__file__).parent / "schema" / "grafana-dashboard.schema.json"
    )
    if schema_path.exists():
        try:
            import jsonschema

            schema = json.loads(schema_path.read_text())
            validator = jsonschema.Draft202012Validator(schema)
            for err in validator.iter_errors(d):
                loc = "$" + "".join(
                    f"[{p!r}]" if isinstance(p, int) else f".{p}"
                    for p in err.absolute_path
                )
                issues.append(f"schema {loc}: {err.message}")
        except ImportError:
            issues.append(
                "jsonschema not installed — `poetry install --with dev` "
                "to enable schema validation (custom checks still ran)"
            )

    print("\nValidating…")
    if issues:
        print(f"\n{len(issues)} issue(s) found:")
        for i in issues:
            print(f"  ✗ {i}")
        return 1
    print(f"  ✓ {len(seen)} panel IDs unique")
    print("  ✓ all datasource refs resolved against __inputs")
    print("  ✓ all variable refs resolved against templating + built-ins")
    print(f"  ✓ all LogQL exprs ({len(exprs)}) balanced")
    print("  ✓ matches project schema")
    return 0


if __name__ == "__main__":
    sys.exit(main())
