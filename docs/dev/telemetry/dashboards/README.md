# Grafana Dashboards

JSON models for DraftForge Grafana Cloud dashboards. Import into Grafana via
**Dashboards → New → Import → Upload JSON file**.

## Subsystem Logs

File: [`subsystem-logs.json`](subsystem-logs.json)
UID: `draftforge-subsystem-logs`

What it shows, sliced by the project's `system` / `subsystem` structlog
taxonomy (see [logging.md](../logging.md) and the `logging` skill):

| Panel | Type | Purpose |
|-------|------|---------|
| Subsystem inventory — events in range | table | Every `(system, subsystem)` tuple seen, with event count. Surfaces newly-added and silently-dropped subsystems. |
| Log rate by subsystem | timeseries (stacked) | Per-minute log rate; spikes flag a hot subsystem, flatlines flag a stopped one. |
| Warn + error rate by subsystem | timeseries (bars) | Restricts to `level=~"warning\|error"`. Anything above zero is the first place to look during an incident. |
| Top 20 events | table | Most-frequent `event` names across the selected subsystems. Surfaces noisy events worth de-duping or upgrading to metrics. |
| Recent logs | logs | Live tail with full structured-log JSON view. |

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
