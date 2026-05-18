# Grafana Dashboards

JSON models for DraftForge Grafana Cloud dashboards. Import into Grafana via
**Dashboards → New → Import → Upload JSON file**.

## Subsystem Logs

File: [`subsystem-logs.json`](subsystem-logs.json)
UID: `draftforge-subsystem-logs`

Structure: **one overview row + one repeating row per system**. Grafana
fans out the repeating row automatically — pick 3 systems in the
template var, you get 3 rows; pick all 8, you get 8.

**Overview row** (always at top, never repeats):

| Panel | Type | Purpose |
|-------|------|---------|
| Subsystem inventory | table | Every `(system, subsystem)` tuple seen in range, with event count. Discovers newly-shipped and silently-dropped subsystems. |
| Log rate by system | timeseries (stacked) | Cross-system view of activity. |
| Warn + error rate by system | timeseries (bars) | Cross-system incident scan. |

**Repeating row** — title `system: $system`, generated once per selected system:

| Panel | Type | Purpose |
|-------|------|---------|
| `$system` — log rate by subsystem | timeseries (stacked) | Hot vs flatlined subsystems within this system. |
| `$system` — warn + error rate by subsystem | timeseries (bars) | Errors and warnings within this system. |
| `$system` — recent logs | logs | Live tail filtered to this system. |

Template variables (cascade left to right):

- **Environment** (`$env`) — single-select Loki label `deployment_environment`. Defaults to `prod`.
- **Service** (`$service`) — multi-select `service_name` filtered to the chosen env. Defaults to `All`.
- **System** (`$system`) — multi-select, queried from the JSON `system` field within the chosen service/env.
- **Subsystem** (`$subsystem`) — multi-select, queried from the JSON `subsystem` field within the chosen system.
- **Level** (`$level`) — multi-select from `debug|info|warning|error`. Defaults to `info,warning,error`.

### Import

1. Open Grafana → **Dashboards** → **New** → **Import**.
2. **Upload JSON file** → `docs/dev/telemetry/dashboards/subsystem-logs.json`.
3. When prompted, map `${DS_LOKI}` to the project's Loki datasource (the
   one labelled `grafanacloudloki` in the data-source picker).
4. Save. The UID is pinned to `draftforge-subsystem-logs`, so re-importing
   overwrites cleanly instead of creating duplicates.

### Updating

Edit the JSON in this repo, push, then re-import (same Upload JSON flow).
Grafana keeps the dashboard's saved state independent of the file — exporting
back from Grafana ("Save → Export → Save to file" or the API) lets you commit
your in-UI tweaks back here.

### Why a structured-log dashboard?

All backend logs are emitted via structlog with mandatory `system` and
`subsystem` kwargs. The dashboard's whole job is to make that taxonomy
browsable in three motions:

1. **Did the new subsystem you just shipped actually fire?** → panel 1.
2. **What's loud or quiet right now?** → panels 2 and 3.
3. **What does a specific event payload look like?** → panel 5 (live tail).

If you add a new `(system, subsystem)` tuple in code, also add the row to
the taxonomy table in `.claude/skills/logging/SKILL.md` — the dashboard will
auto-discover it from log volume, but the skill is the canonical inventory.
