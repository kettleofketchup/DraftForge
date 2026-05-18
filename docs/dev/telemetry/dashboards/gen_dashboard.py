"""Generate the DraftForge subsystem-logs dashboard JSON.

Replaces the dynamic `repeat: "system"` row with a static row per
system in the canonical taxonomy. Adds a Top errors panel to the
overview. JSON parse errors row stays at the bottom.
"""

import json
from pathlib import Path

OUTPUT = Path(
    "/home/kettle/git_repos/draftforge/docs/dev/telemetry/dashboards/subsystem-logs.json"
)

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

DS_LOKI = "${DS_LOKI}"
SERVICE_FILTER = (
    '{service_name=~"$service", deployment_environment="$env"}'
)
# `| __error__=""` drops jsonparsererr series so they don't poison
# aggregations or pop a frontend error toast.
SAFE_JSON = "| json | __error__=\"\""


def _ts_panel(panel_id, x, y, w, h, title, expr, draw_style="line",
              fill_opacity=10, stacking=True, error_threshold=False, description=""):
    """Standard timeseries panel."""
    overrides = []
    thresholds = [{"color": "green", "value": None}]
    if error_threshold:
        thresholds.append({"color": "red", "value": 0.001})
    return {
        "datasource": {"type": "loki", "uid": DS_LOKI},
        "description": description,
        "fieldConfig": {
            "defaults": {
                "color": {"mode": "palette-classic"},
                "custom": {
                    "axisBorderShow": False,
                    "axisCenteredZero": False,
                    "axisColorMode": "text",
                    "axisLabel": "",
                    "axisPlacement": "auto",
                    "barAlignment": 0,
                    "drawStyle": draw_style,
                    "fillOpacity": fill_opacity,
                    "gradientMode": "none",
                    "hideFrom": {"legend": False, "tooltip": False, "viz": False},
                    "insertNulls": False,
                    "lineInterpolation": "linear",
                    "lineWidth": 1,
                    "pointSize": 5,
                    "scaleDistribution": {"type": "linear"},
                    "showPoints": "never",
                    "spanNulls": False,
                    "stacking": {"group": "A", "mode": "normal" if stacking else "none"},
                    "thresholdsStyle": {"mode": "off"},
                },
                "mappings": [],
                "thresholds": {"mode": "absolute", "steps": thresholds},
                "unit": "logs/s",
            },
            "overrides": overrides,
        },
        "gridPos": {"h": h, "w": w, "x": x, "y": y},
        "id": panel_id,
        "options": {
            "legend": {
                "calcs": ["lastNotNull", "max"],
                "displayMode": "table",
                "placement": "right",
                "showLegend": True,
            },
            "tooltip": {"mode": "multi", "sort": "desc"},
        },
        "pluginVersion": "10.4.0",
        "targets": [
            {
                "datasource": {"type": "loki", "uid": DS_LOKI},
                "editorMode": "code",
                "expr": expr,
                "legendFormat": "{{subsystem}}",
                "queryType": "range",
                "refId": "A",
            }
        ],
        "title": title,
        "type": "timeseries",
    }


def _logs_panel(panel_id, x, y, w, h, title, expr, description=""):
    return {
        "datasource": {"type": "loki", "uid": DS_LOKI},
        "description": description,
        "gridPos": {"h": h, "w": w, "x": x, "y": y},
        "id": panel_id,
        "options": {
            "dedupStrategy": "none",
            "enableLogDetails": True,
            "prettifyLogMessage": True,
            "showCommonLabels": False,
            "showLabels": False,
            "showTime": True,
            "sortOrder": "Descending",
            "wrapLogMessage": True,
        },
        "pluginVersion": "10.4.0",
        "targets": [
            {
                "datasource": {"type": "loki", "uid": DS_LOKI},
                "editorMode": "code",
                "expr": expr,
                "queryType": "range",
                "refId": "A",
            }
        ],
        "title": title,
        "type": "logs",
    }


def _table_panel(panel_id, x, y, w, h, title, expr, value_display="Events",
                 description="", organize_index=None):
    overrides = [
        {
            "matcher": {"id": "byName", "options": "Value"},
            "properties": [
                {
                    "id": "custom.cellOptions",
                    "value": {"mode": "gradient", "type": "gauge"},
                },
                {"id": "displayName", "value": value_display},
            ],
        }
    ]
    transformations = []
    if organize_index:
        transformations = [
            {
                "id": "organize",
                "options": {
                    "excludeByName": {"Time": True},
                    "indexByName": organize_index,
                    "renameByName": {},
                },
            }
        ]
    return {
        "datasource": {"type": "loki", "uid": DS_LOKI},
        "description": description,
        "fieldConfig": {
            "defaults": {
                "color": {"mode": "thresholds"},
                "custom": {
                    "align": "auto",
                    "cellOptions": {"type": "auto"},
                    "inspect": False,
                },
                "mappings": [],
                "thresholds": {
                    "mode": "absolute",
                    "steps": [{"color": "green", "value": None}],
                },
            },
            "overrides": overrides,
        },
        "gridPos": {"h": h, "w": w, "x": x, "y": y},
        "id": panel_id,
        "options": {
            "cellHeight": "sm",
            "footer": {
                "countRows": False,
                "fields": "",
                "reducer": ["sum"],
                "show": False,
            },
            "showHeader": True,
            "sortBy": [{"desc": True, "displayName": value_display}],
        },
        "pluginVersion": "10.4.0",
        "targets": [
            {
                "datasource": {"type": "loki", "uid": DS_LOKI},
                "editorMode": "code",
                "expr": expr,
                "instant": True,
                "legendFormat": "",
                "queryType": "instant",
                "refId": "A",
            }
        ],
        "title": title,
        "transformations": transformations,
        "type": "table",
    }


def _row(panel_id, y, title, collapsed=False, panels=None):
    return {
        "collapsed": collapsed,
        "gridPos": {"h": 1, "w": 24, "x": 0, "y": y},
        "id": panel_id,
        "panels": panels or [],
        "title": title,
        "type": "row",
    }


# ---- Overview row + panels ------------------------------------------------

OVERVIEW_PANELS = []

# Subsystem inventory
OVERVIEW_PANELS.append(
    _table_panel(
        panel_id=101,
        x=0, y=1, w=8, h=10,
        title="Subsystem inventory",
        expr=(
            f"sum by (system, subsystem) (count_over_time("
            f"{SERVICE_FILTER} {SAFE_JSON} | system!=\"\" [$__range]))"
        ),
        description=(
            "Every (system, subsystem) tuple seen in range. Surfaces "
            "newly-shipped subsystems and silently-dropped ones."
        ),
        organize_index={"system": 0, "subsystem": 1, "Value": 2},
    )
)

# Top error messages
OVERVIEW_PANELS.append(
    _table_panel(
        panel_id=104,
        x=8, y=1, w=16, h=10,
        title="Top error messages",
        expr=(
            f"topk(20, sum by (event, system, subsystem) (count_over_time("
            f"{SERVICE_FILTER} {SAFE_JSON} "
            f"| level=~\"warning|error\" [$__range])))"
        ),
        value_display="Count",
        description=(
            "Most frequent warn/error events. Top of this list is "
            "where to spend the next round of fixes."
        ),
        organize_index={
            "event": 0, "system": 1, "subsystem": 2, "Value": 3,
        },
    )
)

# Log rate by system
OVERVIEW_PANELS.append(
    _ts_panel(
        panel_id=102,
        x=0, y=11, w=12, h=8,
        title="Log rate by system",
        expr=(
            f"sum by (system) (rate("
            f"{SERVICE_FILTER} {SAFE_JSON} | system!=\"\" [$__interval]))"
        ),
        description="Total log rate aggregated by system.",
    )
)
# Override legend to show {{system}} for this overview panel
OVERVIEW_PANELS[-1]["targets"][0]["legendFormat"] = "{{system}}"

# Warn + error rate by system
OVERVIEW_PANELS.append(
    _ts_panel(
        panel_id=103,
        x=12, y=11, w=12, h=8,
        title="Warn + error rate by system",
        expr=(
            f"sum by (system) (rate("
            f"{SERVICE_FILTER} {SAFE_JSON} "
            f"| system!=\"\" | level=~\"warning|error\" [$__interval]))"
        ),
        draw_style="bars",
        fill_opacity=70,
        error_threshold=True,
        description=(
            "Warn + error rate aggregated by system. First place to "
            "look during an incident."
        ),
    )
)
OVERVIEW_PANELS[-1]["targets"][0]["legendFormat"] = "{{system}}"


# ---- Per-system rows (one static row per system) --------------------------

def system_row(system: str, base_id: int, y: int):
    """Build a collapsed row containing 3 panels for one system."""
    expr_log_rate = (
        f"sum by (subsystem) (rate("
        f"{SERVICE_FILTER} {SAFE_JSON} "
        f"| system=\"{system}\" | subsystem!=\"\" [$__interval]))"
    )
    expr_err_rate = (
        f"sum by (subsystem) (rate("
        f"{SERVICE_FILTER} {SAFE_JSON} "
        f"| system=\"{system}\" | subsystem!=\"\" "
        f"| level=~\"warning|error\" [$__interval]))"
    )
    expr_logs = (
        f"{SERVICE_FILTER} {SAFE_JSON} "
        f"| system=\"{system}\" | subsystem=~\"$subsystem\" "
        f"| level=~\"$level\""
    )

    inner = [
        _ts_panel(
            panel_id=base_id + 1, x=0, y=y + 1, w=12, h=8,
            title=f"{system} — log rate by subsystem",
            expr=expr_log_rate,
            description=f"Log rate within the {system} system, grouped by subsystem.",
        ),
        _ts_panel(
            panel_id=base_id + 2, x=12, y=y + 1, w=12, h=8,
            title=f"{system} — warn + error rate by subsystem",
            expr=expr_err_rate,
            draw_style="bars",
            fill_opacity=70,
            error_threshold=True,
            description=(
                f"Warn + error rate within the {system} system, "
                "grouped by subsystem."
            ),
        ),
        _logs_panel(
            panel_id=base_id + 3, x=0, y=y + 9, w=24, h=10,
            title=f"{system} — recent logs",
            expr=expr_logs,
            description=(
                f"Live tail filtered to system={system}. Respects the "
                "global subsystem and level filters."
            ),
        ),
    ]
    return _row(panel_id=base_id, y=y, title=system, collapsed=True, panels=inner)


system_rows = []
y_cursor = 20  # overview row used y=0; panels through y≈19
for i, system in enumerate(SYSTEMS):
    base_id = 1000 + i * 10
    system_rows.append(system_row(system, base_id, y_cursor))
    # Collapsed rows have height 1; only matters when expanded.
    y_cursor += 20


# ---- JSON parse errors row (existing, kept verbatim) ----------------------

JSON_ERR_PANELS = [
    _logs_panel(
        panel_id=301, x=0, y=y_cursor + 1, w=24, h=10,
        title="Lines that broke `| json` (jsonparsererr)",
        expr=(
            f"{SERVICE_FILTER} | json | __error__=\"jsonparsererr\""
        ),
        description=(
            "Log lines that Loki's `| json` parser rejects. Source labels "
            "(code_file_path, code_function_name, code_line_number) tell "
            "you which Python file is emitting broken JSON — usually an "
            "f-string containing a stray `{` like a dict literal or repr() "
            "output. Fix at source by switching the call to structlog kwargs."
        ),
    ),
    _table_panel(
        panel_id=302, x=0, y=y_cursor + 11, w=24, h=8,
        title="Top sources of broken JSON",
        expr=(
            f"topk(20, sum by (code_file_path, code_function_name, "
            f"code_line_number) (count_over_time("
            f"{SERVICE_FILTER} | json | __error__=\"jsonparsererr\" "
            f"[$__range])))"
        ),
        value_display="Bad lines",
        description=(
            "Which source files are emitting broken JSON, ranked by count. "
            "Fix the top entries at source."
        ),
        organize_index={
            "code_file_path": 0,
            "code_function_name": 1,
            "code_line_number": 2,
            "Value": 3,
        },
    ),
]

json_err_row = _row(
    panel_id=300, y=y_cursor, title="JSON parse errors (collapsed)",
    collapsed=True, panels=JSON_ERR_PANELS,
)


# ---- Assemble dashboard ---------------------------------------------------

dashboard = {
    "__inputs": [
        {
            "name": "DS_LOKI",
            "label": "Loki",
            "description": "Loki datasource (e.g. grafanacloudloki)",
            "type": "datasource",
            "pluginId": "loki",
            "pluginName": "Loki",
        }
    ],
    "__elements": {},
    "__requires": [
        {"type": "grafana", "id": "grafana", "name": "Grafana", "version": "10.4.0"},
        {"type": "datasource", "id": "loki", "name": "Loki", "version": "1.0.0"},
        {"type": "panel", "id": "logs", "name": "Logs", "version": ""},
        {"type": "panel", "id": "table", "name": "Table", "version": ""},
        {"type": "panel", "id": "timeseries", "name": "Time series", "version": ""},
        {"type": "panel", "id": "row", "name": "Row", "version": ""},
    ],
    "annotations": {
        "list": [
            {
                "builtIn": 1,
                "datasource": {"type": "grafana", "uid": "-- Grafana --"},
                "enable": True,
                "hide": True,
                "iconColor": "rgba(0, 211, 255, 1)",
                "name": "Annotations & Alerts",
                "type": "dashboard",
            }
        ]
    },
    "description": (
        "DraftForge structured-log dashboard. Overview row at the top "
        "summarizes inventory, log rate, warn/error rate, and top error "
        "events. Each system in the canonical taxonomy gets its own "
        "collapsed row below — expand the one you care about. Bottom row "
        "surfaces lines that fail `| json` parsing so we can fix them at "
        "source. See .claude/skills/logging/SKILL.md for the taxonomy."
    ),
    "editable": True,
    "fiscalYearStartMonth": 0,
    "graphTooltip": 1,
    "id": None,
    "links": [],
    "panels": [
        _row(panel_id=100, y=0, title="Overview — all systems", collapsed=False),
        *OVERVIEW_PANELS,
        *system_rows,
        json_err_row,
    ],
    "refresh": "30s",
    "schemaVersion": 39,
    "tags": ["draftforge", "logs", "structlog"],
    "templating": {
        "list": [
            {
                "current": {"selected": False, "text": "prod", "value": "prod"},
                "datasource": {"type": "loki", "uid": DS_LOKI},
                "definition": "label_values(deployment_environment)",
                "hide": 0,
                "includeAll": False,
                "label": "Environment",
                "multi": False,
                "name": "env",
                "options": [],
                "query": {
                    "label": "deployment_environment",
                    "refId": "LokiVariableQueryEditor-VariableQuery",
                    "stream": "",
                    "type": 1,
                },
                "refresh": 1,
                "regex": "",
                "skipUrlSync": False,
                "sort": 0,
                "type": "query",
            },
            {
                "current": {
                    "selected": True,
                    "text": ["All"],
                    "value": ["$__all"],
                },
                "datasource": {"type": "loki", "uid": DS_LOKI},
                "definition": (
                    "label_values({deployment_environment=\"$env\"}, "
                    "service_name)"
                ),
                "hide": 0,
                "includeAll": True,
                "label": "Service",
                "multi": True,
                "name": "service",
                "options": [],
                "query": {
                    "label": "service_name",
                    "refId": "LokiVariableQueryEditor-VariableQuery",
                    "stream": "{deployment_environment=\"$env\"}",
                    "type": 1,
                },
                "refresh": 1,
                "regex": "",
                "skipUrlSync": False,
                "sort": 1,
                "type": "query",
            },
            {
                "current": {
                    "selected": True,
                    "text": ["All"],
                    "value": ["$__all"],
                },
                "description": (
                    "Global subsystem filter — applies to the recent-logs "
                    "panels inside each system row."
                ),
                "hide": 0,
                "includeAll": True,
                "label": "Subsystem",
                "multi": True,
                "name": "subsystem",
                "options": [],
                "query": "",
                "refresh": 0,
                "skipUrlSync": False,
                "type": "textbox",
            },
            {
                "current": {
                    "selected": True,
                    "text": ["info", "warning", "error"],
                    "value": ["info", "warning", "error"],
                },
                "hide": 0,
                "includeAll": True,
                "label": "Level",
                "multi": True,
                "name": "level",
                "options": [
                    {"selected": False, "text": "All", "value": "$__all"},
                    {"selected": False, "text": "debug", "value": "debug"},
                    {"selected": True, "text": "info", "value": "info"},
                    {"selected": True, "text": "warning", "value": "warning"},
                    {"selected": True, "text": "error", "value": "error"},
                ],
                "query": "debug,info,warning,error",
                "queryValue": "",
                "skipUrlSync": False,
                "type": "custom",
            },
        ]
    },
    "time": {"from": "now-3h", "to": "now"},
    "timepicker": {},
    "timezone": "browser",
    "title": "DraftForge — Subsystem Logs",
    "uid": "draftforge-subsystem-logs",
    "version": 5,
    "weekStart": "",
}

OUTPUT.write_text(json.dumps(dashboard, indent=2) + "\n")
print(f"Wrote {OUTPUT}")
print(f"Systems: {len(SYSTEMS)}")
print(f"Total panels (incl. rows): {len(dashboard['panels'])}")


# ---- Validation -----------------------------------------------------------
# Grafana doesn't publish a stable JSON schema for dashboard models (Cue
# schemas live in-tree but aren't versioned for external consumers). The
# grafana skill (`.claude/skills/grafana/SKILL.md` → Dashboard Review
# section) enumerates the bugs that actually break dashboards at import
# time, which is what we check for here.

import sys


def validate(d: dict) -> list[str]:
    errors: list[str] = []

    # --- Top-level shape ----------------------------------------------------
    for key in ("panels", "templating", "title", "uid", "schemaVersion"):
        if key not in d:
            errors.append(f"top-level: missing required key {key!r}")

    # --- Panel IDs and grid positions --------------------------------------
    seen_ids: dict[int, str] = {}

    def visit_panel(p: dict, parent_title: str = "") -> None:
        pid = p.get("id")
        if pid is None:
            errors.append(
                f"panel {parent_title!r} {p.get('title','?')!r}: missing 'id'"
            )
            return
        if pid in seen_ids:
            errors.append(
                f"duplicate panel id {pid}: {seen_ids[pid]!r} and "
                f"{p.get('title','?')!r}"
            )
        else:
            seen_ids[pid] = p.get("title", "?")
        if "gridPos" not in p:
            errors.append(
                f"panel id={pid} {p.get('title','?')!r}: missing 'gridPos'"
            )
        if "type" not in p:
            errors.append(
                f"panel id={pid} {p.get('title','?')!r}: missing 'type'"
            )
        for inner in p.get("panels", []) or []:
            visit_panel(inner, parent_title=f"row id={pid}")

    for p in d.get("panels", []):
        visit_panel(p)

    # --- Datasource references --------------------------------------------
    declared_inputs = {i["name"] for i in d.get("__inputs", [])}
    ds_refs: set[str] = set()

    def walk_ds(o):
        if isinstance(o, dict):
            if (
                "uid" in o
                and isinstance(o.get("uid"), str)
                and o["uid"].startswith("${")
                and o["uid"].endswith("}")
            ):
                ds_refs.add(o["uid"][2:-1])
            for v in o.values():
                walk_ds(v)
        elif isinstance(o, list):
            for x in o:
                walk_ds(x)

    walk_ds(d)
    for ref in ds_refs:
        if ref not in declared_inputs:
            errors.append(
                f"datasource ${{{ref}}} referenced but not declared in __inputs"
            )

    # --- Template variable references in expressions ----------------------
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
    import re as _re

    var_re = _re.compile(r"\$(?:\{)?([A-Za-z_][A-Za-z0-9_]*)")
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
            errors.append(
                f"expr {path}: references $${name} which is not a template "
                f"variable or known Grafana built-in"
            )

    # --- LogQL paren/brace/bracket/backtick balance -----------------------
    for path, e in exprs:
        po, pc = e.count("("), e.count(")")
        bo, bc = e.count("{"), e.count("}")
        so, sc = e.count("["), e.count("]")
        bt = e.count("`")
        if po != pc:
            errors.append(
                f"expr {path}: paren imbalance ({po} `(` vs {pc} `)`)"
            )
        if bo != bc:
            errors.append(
                f"expr {path}: brace imbalance ({bo} `{{` vs {bc} `}}`)"
            )
        if so != sc:
            errors.append(
                f"expr {path}: bracket imbalance ({so} `[` vs {sc} `]`)"
            )
        if bt % 2 != 0:
            errors.append(f"expr {path}: odd backtick count ({bt})")

    return errors


print("\nValidating…")
issues = validate(dashboard)
if issues:
    print(f"\n{len(issues)} issue(s) found:")
    for i in issues:
        print(f"  ✗ {i}")
    sys.exit(1)
print(f"  ✓ {len(seen_ids := {p['id'] for p in dashboard['panels']})} top-level panel/row IDs")
print(f"  ✓ all datasource refs resolved against __inputs")
print(f"  ✓ all template vars resolved against templating.list + Grafana built-ins")
print("  ✓ all LogQL exprs balanced")
