"""Generate the DraftForge subsystem-logs dashboard JSON (V2 / Scenes).

Targets Grafana's `dashboard.grafana.app/v2beta1` schema (Dynamic
Dashboards, GA April 2026). V1 dashboards still import but Grafana
Cloud's JSON editor blocks save/apply with "Missing property" errors
against the V2 schema — this generator emits V2 directly so editing
in-app works.

Structure:
* Top-level envelope: {apiVersion, kind, metadata, spec}.
* spec.elements: dict of {panel-name: Panel}.
* spec.layout: RowsLayout containing one Row per system + an Overview
  row at the top and a JSON-parse-errors row at the bottom.
* Each Row's inner layout is a Grid referencing panel names via
  ElementReference.

Re-run after editing — self-validates and exits 1 on structural problems.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from grafana_foundation_sdk.builders import (
    common as common_builder,
    dashboardv2beta1 as v2,
    logs as logs_b,
    loki,
    table as table_b,
    timeseries as timeseries_b,
)
from grafana_foundation_sdk.cog.encoder import JSONEncoder
from grafana_foundation_sdk.models.common import (
    BarGaugeDisplayMode,
    GraphDrawStyle,
    LegendDisplayMode,
    LegendPlacement,
    StackingMode,
    TableBarGaugeCellOptions,
    TooltipDisplayMode,
)
from grafana_foundation_sdk.models.dashboard import DataSourceRef
from grafana_foundation_sdk.models.dashboardv2beta1 import (
    DashboardCursorSync,
    DataQueryKind,
    Dashboardv2beta1DataQueryKindDatasource,
    VariableRefresh,
)


# V2's DataQueryKind envelope. The SDK's per-datasource builders
# (loki.Dataquery, prometheus.Dataquery, etc.) emit V1-shaped query
# bodies — we have to wrap them in the V2 envelope ourselves or
# Grafana Cloud's V2 validator rejects with
# `spec.query.kind: conflicting values "DataQuery" and ""`.
#
# Datasource handling note: V2 dashboards do not support the V1
# `__inputs` import-time substitution. Instead we declare a
# `DatasourceVariable` named `ds_loki` (filtered to plugin_id="loki")
# which renders as a dropdown in the dashboard header. Panels then
# reference the variable via `$ds_loki` in their datasource.name field.
LOKI_DS_VAR = "$ds_loki"


class _LokiQuery:
    """Builder shim that wraps a loki.Dataquery in DataQueryKind for V2."""

    def __init__(self, expr: str, *, legend: str = "", instant: bool = False):
        spec: dict = {"expr": expr, "editorMode": "code", "refId": "A"}
        if legend:
            spec["legendFormat"] = legend
        if instant:
            spec["queryType"] = "instant"
            spec["instant"] = True
        self._internal = DataQueryKind(
            group="loki",
            version="v1",
            datasource=Dashboardv2beta1DataQueryKindDatasource(name=LOKI_DS_VAR),
            spec=spec,
        )

    def build(self) -> DataQueryKind:
        return self._internal

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

# `${DS_LOKI}` is substituted by Grafana's import dialog from the
# __inputs block we post-process in.
DS_LOKI = DataSourceRef(type_val="loki", uid="${DS_LOKI}")
SERVICE_FILTER = '{service=~"$service", deployment_environment=~"$env"}'
# `| __error__=""` drops jsonparsererr series so they don't poison
# aggregations or pop a frontend error toast.
SAFE_JSON = '| json | __error__=""'


# ---- Query helpers --------------------------------------------------------


def _loki_query(expr: str, legend: str = "", *, instant: bool = False) -> _LokiQuery:
    """Loki query wrapped in V2 DataQueryKind envelope."""
    return _LokiQuery(expr, legend=legend, instant=instant)


def _query_group(expr: str, legend: str = "", *, instant: bool = False) -> v2.QueryGroup:
    """V2 QueryGroup wrapping a single Loki target."""
    return v2.QueryGroup().target(
        v2.Target().ref_id("A").query(_loki_query(expr, legend, instant=instant))
    )


# ---- Visualization helpers (V2 VizConfigKind builders) -------------------


def _legend_opts() -> common_builder.VizLegendOptions:
    """Right-side table legend with last + max calcs."""
    return (
        common_builder.VizLegendOptions()
        .show_legend(True)
        .placement(LegendPlacement.RIGHT)
        .display_mode(LegendDisplayMode.TABLE)
        .calcs(["lastNotNull", "max"])
    )


def _tooltip_opts() -> common_builder.VizTooltipOptions:
    """Multi-series tooltip sorted desc."""
    return (
        common_builder.VizTooltipOptions()
        .mode(TooltipDisplayMode.MULTI)
        .sort("desc")
    )


def _ts_viz(
    *,
    draw_style: GraphDrawStyle = GraphDrawStyle.LINE,
    fill_opacity: int = 10,
) -> timeseries_b.Visualization:
    """Stacked timeseries visualization with project defaults."""
    return (
        timeseries_b.Visualization()
        .unit("logs/s")
        .draw_style(draw_style)
        .fill_opacity(fill_opacity)
        .stacking(
            common_builder.StackingConfig().mode(StackingMode.NORMAL).group("A")
        )
        .legend(_legend_opts())
        .tooltip(_tooltip_opts())
    )


def _err_viz() -> timeseries_b.Visualization:
    """Warn+error variant: bars + red threshold at 0.001."""
    return _ts_viz(draw_style=GraphDrawStyle.BARS, fill_opacity=70)


def _logs_viz(*, show_labels: bool = False) -> logs_b.Visualization:
    return (
        logs_b.Visualization()
        .show_time(True)
        .sort_order("Descending")
        .prettify_log_message(True)
        .wrap_log_message(True)
        .enable_log_details(True)
        .show_labels(show_labels)
    )


def _table_viz() -> table_b.Visualization:
    return (
        table_b.Visualization()
        .show_header(True)
        .cell_options(TableBarGaugeCellOptions(mode=BarGaugeDisplayMode.GRADIENT))
        .sort_by([
            common_builder.TableSortByFieldState().display_name("Value").desc(True)
        ])
    )


# ---- Panel factories ------------------------------------------------------


_next_panel_id = iter(range(1, 10_000))


def _ts_panel(
    title: str,
    expr: str,
    *,
    legend: str = "{{subsystem}}",
    description: str = "",
    err: bool = False,
) -> v2.Panel:
    viz = _err_viz() if err else _ts_viz()
    return (
        v2.Panel()
        .id(next(_next_panel_id))
        .title(title)
        .description(description)
        .data(_query_group(expr, legend))
        .visualization(viz)
    )


def _logs_panel(
    title: str,
    expr: str,
    *,
    description: str = "",
    show_labels: bool = False,
) -> v2.Panel:
    return (
        v2.Panel()
        .id(next(_next_panel_id))
        .title(title)
        .description(description)
        .data(_query_group(expr))
        .visualization(_logs_viz(show_labels=show_labels))
    )


def _table_panel(title: str, expr: str, *, description: str = "") -> v2.Panel:
    return (
        v2.Panel()
        .id(next(_next_panel_id))
        .title(title)
        .description(description)
        .data(_query_group(expr, instant=True))
        .visualization(_table_viz())
    )


# ---- Layout helpers -------------------------------------------------------


def _grid_item(name: str, *, x: int, y: int, w: int, h: int) -> v2.GridItem:
    return v2.GridItem().name(name).x(x).y(y).width(w).height(h)


# ---- Overview row ---------------------------------------------------------


def overview_panels() -> dict[str, v2.Panel]:
    inv = _table_panel(
        "Subsystem inventory",
        f"sum by (system, subsystem) (count_over_time("
        f'{SERVICE_FILTER} {SAFE_JSON} | system!="" [$__range]))',
        description=(
            "Every (system, subsystem) tuple seen in range. Surfaces "
            "newly-shipped and silently-dropped subsystems."
        ),
    )
    top_err = _table_panel(
        "Top error messages",
        f"topk(20, sum by (event, system, subsystem) (count_over_time("
        f"{SERVICE_FILTER} {SAFE_JSON} "
        f'| level=~"warning|error" [$__range])))',
        description=(
            "Most frequent warn/error events. Top of this list is where "
            "to spend the next round of fixes."
        ),
    )
    log_rate = _ts_panel(
        "Log rate by system",
        f"sum by (system) (rate("
        f'{SERVICE_FILTER} {SAFE_JSON} | system!="" [$__interval]))',
        legend="{{system}}",
        description="Total log rate aggregated by system.",
    )
    err_rate = _ts_panel(
        "Warn + error rate by system",
        f"sum by (system) (rate("
        f"{SERVICE_FILTER} {SAFE_JSON} "
        f'| system!="" | level=~"warning|error" [$__interval]))',
        legend="{{system}}",
        description=(
            "Warn + error rate aggregated by system. First place to look "
            "during an incident."
        ),
        err=True,
    )
    return {
        "overview-inventory": inv,
        "overview-top-errors": top_err,
        "overview-log-rate": log_rate,
        "overview-err-rate": err_rate,
    }


def overview_grid(names: dict[str, v2.Panel]) -> v2.Grid:
    return (
        v2.Grid()
        .item(_grid_item("overview-inventory",   x=0,  y=0,  w=8,  h=10))
        .item(_grid_item("overview-top-errors",  x=8,  y=0,  w=16, h=10))
        .item(_grid_item("overview-log-rate",    x=0,  y=10, w=12, h=8))
        .item(_grid_item("overview-err-rate",    x=12, y=10, w=12, h=8))
    )


# ---- Per-system row -------------------------------------------------------


def system_panels(system: str) -> dict[str, v2.Panel]:
    return {
        f"{system}-log-rate": _ts_panel(
            f"{system} — log rate by subsystem",
            f"sum by (subsystem) (rate("
            f"{SERVICE_FILTER} {SAFE_JSON} "
            f'| system="{system}" | subsystem!="" [$__interval]))',
            description=f"Log rate within {system}, grouped by subsystem.",
        ),
        f"{system}-err-rate": _ts_panel(
            f"{system} — warn + error rate by subsystem",
            f"sum by (subsystem) (rate("
            f"{SERVICE_FILTER} {SAFE_JSON} "
            f'| system="{system}" | subsystem!="" '
            f'| level=~"warning|error" [$__interval]))',
            description=f"Warn + error rate within {system}, grouped by subsystem.",
            err=True,
        ),
        f"{system}-logs": _logs_panel(
            f"{system} — recent logs",
            f"{SERVICE_FILTER} {SAFE_JSON} "
            f'| system="{system}" | subsystem=~"$subsystem" '
            f'| level=~"$level"',
            description=(
                f"Live tail filtered to system={system}. Respects the "
                "global subsystem and level filters."
            ),
        ),
    }


def system_grid(system: str) -> v2.Grid:
    return (
        v2.Grid()
        .item(_grid_item(f"{system}-log-rate", x=0,  y=0, w=12, h=8))
        .item(_grid_item(f"{system}-err-rate", x=12, y=0, w=12, h=8))
        .item(_grid_item(f"{system}-logs",     x=0,  y=8, w=24, h=10))
    )


# ---- JSON parse errors row ------------------------------------------------


def json_errors_panels() -> dict[str, v2.Panel]:
    return {
        "json-errors-logs": _logs_panel(
            "Lines that broke `| json` (jsonparsererr)",
            f'{SERVICE_FILTER} | json | __error__="jsonparsererr"',
            show_labels=True,
            description=(
                "Log lines that Loki's `| json` parser rejects. Source "
                "labels (code_file_path, code_function_name, "
                "code_line_number) tell you which Python file is emitting "
                "broken JSON — usually an f-string containing a stray `{` "
                "like a dict literal or repr() output. Fix at source by "
                "switching the call to structlog kwargs."
            ),
        ),
        "json-errors-sources": _table_panel(
            "Top sources of broken JSON",
            f"topk(20, sum by (code_file_path, code_function_name, "
            f"code_line_number) (count_over_time("
            f'{SERVICE_FILTER} | json | __error__="jsonparsererr" '
            f"[$__range])))",
            description=(
                "Which source files are emitting broken JSON, ranked by "
                "count. Fix the top entries at source."
            ),
        ),
    }


def json_errors_grid() -> v2.Grid:
    return (
        v2.Grid()
        .item(_grid_item("json-errors-logs",    x=0, y=0,  w=24, h=10))
        .item(_grid_item("json-errors-sources", x=0, y=10, w=24, h=8))
    )


# ---- Variables ------------------------------------------------------------


def build_variables() -> list:
    ds_loki = (
        v2.DatasourceVariable("ds_loki")
        .label("Loki")
        .plugin_id("loki")
        .description(
            "Pick the Loki datasource to point this dashboard at. "
            "Selection persists per-user."
        )
    )
    env = (
        v2.QueryVariable("env")
        .label("Environment")
        .query(_LokiQuery("label_values(deployment_environment)"))
        .refresh(VariableRefresh.ON_DASHBOARD_LOAD)
        # Regex-matched in SERVICE_FILTER so we can `include_all` + use
        # `.+` as the "All" expansion. With equality matching, an
        # unselected env would substitute to "" and Loki would reject
        # the empty-compatible matcher → panels go blank instead of
        # showing all envs.
        .multi(True)
        .include_all(True)
        .all_value(".+")
    )
    # Service query intentionally does NOT filter by $env. Loki rejects
    # stream selectors whose only matchers are empty-compatible (`.*`,
    # `""`), and on first load $env hasn't resolved yet — so a query
    # like `label_values({deployment_environment="$env"}, service)`
    # becomes `{deployment_environment=""}` and gets refused before
    # the cascading variable can populate. Listing all services across
    # envs is fine for our usage; panel queries still constrain to
    # the selected $env via the equality matcher in SERVICE_FILTER.
    service = (
        v2.QueryVariable("service")
        .label("Service")
        .query(_LokiQuery("label_values(service)"))
        .refresh(VariableRefresh.ON_DASHBOARD_LOAD)
        .multi(True)
        .include_all(True)
        # `All` expands to all_value verbatim. `.+` (one-or-more) is
        # non-empty-compatible so Loki accepts the matcher; `.*` (the
        # default) is empty-compatible and gets rejected.
        .all_value(".+")
    )
    subsystem = (
        v2.TextVariable("subsystem")
        .label("Subsystem")
        .description(
            "Regex filter applied to recent-logs panels. Empty matches all."
        )
    )
    level = (
        v2.CustomVariable("level")
        .label("Level")
        .query("debug,info,warning,error")
        .multi(True)
        .include_all(True)
    )
    # ds_loki goes first so the user picks the datasource before any
    # downstream query variable fires.
    return [ds_loki, env, service, subsystem, level]


# ---- Time settings --------------------------------------------------------


def build_time_settings() -> v2.TimeSettings:
    return (
        v2.TimeSettings()
        .from_val("now-3h")
        .to("now")
        .auto_refresh("30s")
        .timezone("browser")
    )


# ---- Top-level build ------------------------------------------------------


def build_dashboard():
    # Collect every panel and its element-name in one pass so we can both
    # register them with .element() and reference them from grid items.
    elements: dict[str, v2.Panel] = {}
    elements.update(overview_panels())
    for system in SYSTEMS:
        elements.update(system_panels(system))
    elements.update(json_errors_panels())

    # Rows layout: overview at top (expanded), system rows (collapsed), then
    # the JSON parse errors row (collapsed).
    rows = v2.Rows()
    rows = rows.row(
        v2.Row().title("Overview — all systems").collapse(False).layout(overview_grid({}))
    )
    for system in SYSTEMS:
        rows = rows.row(
            v2.Row().title(system).collapse(True).layout(system_grid(system))
        )
    rows = rows.row(
        v2.Row()
        .title("JSON parse errors (collapsed)")
        .collapse(True)
        .layout(json_errors_grid())
    )

    builder = (
        v2.Dashboard("DraftForge — Subsystem Logs")
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
        .editable(True)
        .preload(False)
        .live_now(False)
        .cursor_sync(DashboardCursorSync.OFF)
        .time_settings(build_time_settings())
        .layout(rows)
    )
    for name, panel in elements.items():
        builder = builder.element(name, panel)
    for var in build_variables():
        builder = builder.variable(var)
    return builder


def post_process(dashboard_spec: dict, *, uid: str) -> dict:
    """Wrap the SDK's spec output in the V2 envelope.

    SDK's .build() returns just the `spec` body. Grafana's V2 schema
    expects `{apiVersion, kind, metadata, spec}` at the root. V2 drops
    the V1 `__inputs` import-time substitution — datasource selection
    is now a runtime DatasourceVariable inside spec.variables instead.
    """
    return {
        "apiVersion": "dashboard.grafana.app/v2beta1",
        "kind": "Dashboard",
        "metadata": {"name": uid},
        "spec": dashboard_spec,
    }


def main() -> int:
    spec = json.loads(JSONEncoder(sort_keys=False, indent=2).encode(build_dashboard().build()))
    full = post_process(spec, uid="draftforge-subsystem-logs")
    OUTPUT.write_text(json.dumps(full, indent=2) + "\n")

    print(f"Wrote {OUTPUT}")
    print(f"Systems: {len(SYSTEMS)}")
    print(f"Elements: {len(spec.get('elements', {}))}")
    print(f"Rows in layout: {len(spec.get('layout', {}).get('spec', {}).get('rows', []))}")
    return validate(full)


# ---- Validation -----------------------------------------------------------


def validate(d: dict) -> int:
    issues: list[str] = []

    # Envelope
    for k in ("apiVersion", "kind", "metadata", "spec"):
        if k not in d:
            issues.append(f"envelope: missing {k!r}")
    if d.get("apiVersion") != "dashboard.grafana.app/v2beta1":
        issues.append(
            f"envelope: apiVersion={d.get('apiVersion')!r} (expected v2beta1)"
        )

    spec = d.get("spec", {})

    # Required spec fields (V2 schema)
    for k in (
        "title",
        "layout",
        "elements",
        "cursorSync",
        "timeSettings",
        "variables",
        "annotations",
        "links",
        "preload",
        "editable",
        "tags",
    ):
        if k not in spec:
            issues.append(f"spec: missing required field {k!r}")

    # Element names referenced in layout grid items must exist in spec.elements
    elements = spec.get("elements", {})
    if not isinstance(elements, dict):
        issues.append("spec.elements is not a dict")
    referenced_names: set[str] = set()

    def walk_layout(layout):
        if not isinstance(layout, dict):
            return
        sub_spec = layout.get("spec", {})
        for row in sub_spec.get("rows", []) or []:
            walk_layout(row.get("spec", {}).get("layout", {}))
        for item in sub_spec.get("items", []) or []:
            n = item.get("spec", {}).get("element", {}).get("name")
            if n:
                referenced_names.add(n)

    walk_layout(spec.get("layout", {}))
    for n in referenced_names:
        if n not in elements:
            issues.append(f"layout references element {n!r} but it's not in spec.elements")
    unreferenced = set(elements.keys()) - referenced_names
    for n in unreferenced:
        issues.append(f"element {n!r} declared but never referenced by layout")

    # Panel id uniqueness across elements
    seen_ids: dict[int, str] = {}
    for name, el in elements.items():
        if not isinstance(el, dict):
            continue
        pid = el.get("spec", {}).get("id")
        if pid is None:
            issues.append(f"element {name!r}: missing spec.id")
            continue
        if pid in seen_ids:
            issues.append(
                f"duplicate panel id {pid}: {seen_ids[pid]!r} and {name!r}"
            )
        else:
            seen_ids[pid] = name

    # LogQL balance + variable refs. In V2 we use a DatasourceVariable
    # `ds_loki` rather than V1's __inputs substitution; pick it up from
    # spec.variables so the validator doesn't flag $ds_loki as unknown.
    declared_vars = {v.get("spec", {}).get("name") for v in spec.get("variables", [])}
    declared_vars.discard(None)
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
                f"expr {path}: references ${name} which is not a declared "
                f"variable or known Grafana built-in"
            )
        if expr.count("(") != expr.count(")"):
            issues.append(f"expr {path}: paren imbalance")
        if expr.count("{") != expr.count("}"):
            issues.append(f"expr {path}: brace imbalance")
        if expr.count("[") != expr.count("]"):
            issues.append(f"expr {path}: bracket imbalance")

    print("\nValidating…")
    if issues:
        print(f"\n{len(issues)} issue(s) found:")
        for i in issues:
            print(f"  ✗ {i}")
        return 1
    print(f"  ✓ envelope: apiVersion={d['apiVersion']}")
    print(f"  ✓ spec has all V2 required fields")
    print(f"  ✓ {len(seen_ids)} elements with unique panel IDs")
    print(f"  ✓ all {len(referenced_names)} layout references resolve")
    print(f"  ✓ all {len(exprs)} LogQL exprs balanced + variable refs resolve")
    return 0


if __name__ == "__main__":
    sys.exit(main())
