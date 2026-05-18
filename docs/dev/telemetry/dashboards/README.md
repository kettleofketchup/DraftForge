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

### Updating an existing dashboard from new JSON

Three ways, fastest first. Use whichever fits — the UID is pinned to
`draftforge-subsystem-logs`, so all three target the same dashboard.

1. **In-place via JSON Model (recommended)** — preserves URL, panel history,
   and any in-UI tweaks not yet rolled back into the repo:
   - Open the dashboard.
   - ⚙️ **Dashboard settings** → **JSON Model**.
   - Replace the whole JSON with the file contents.
   - **Save changes**.

2. **Re-import** — overwrites cleanly because the UID matches:
   - Dashboards → New → **Import** → **Upload JSON file**.
   - Confirm "Overwrite existing dashboard with same UID".

3. **API** — for scripted updates:
   ```bash
   curl -X POST \
     -H "Authorization: Bearer $GRAFANA_TOKEN" \
     -H "Content-Type: application/json" \
     "$GRAFANA_URL/api/dashboards/db" \
     -d "$(jq '{dashboard: ., overwrite: true}' subsystem-logs.json)"
   ```

To capture in-UI tweaks back into the repo: open the dashboard → ⚙️ →
**Save → Export → Save to file** (untick "Export for sharing externally"
if you want the existing `__inputs` block kept), then commit the diff.

### Collapsed "JSON parse errors" row

At the bottom there's a collapsed row labelled **JSON parse errors
(collapsed)**. Expand it when:

- A panel suddenly shows fewer series than expected.
- Legends collapse to a generic `Value` label instead of one per system.
- The `system` template variable returns fewer options than the
  taxonomy table in `.claude/skills/logging/SKILL.md` says exist.

All three symptoms have the same root cause: one or more Python log
calls in the stream emit messages with stray `{` or `}` characters (an
f-string that interpolated a dict, an unstructured `repr()`, etc.).
Loki's `| json` parser rejects those lines and they never reach the
panel filters that group by `system`/`subsystem`.

The row contains:

- **Lines that broke `| json`** — every offending log line with full
  context labels (`code_file_path`, `code_function_name`,
  `code_line_number`). Click into one to see the raw message.
- **Top sources of broken JSON** — ranked table of `(file, line,
  function)` tuples. Fix the top entries at source by migrating the
  call from stdlib `logging` + f-string to `telemetry.logging.get_logger`
  + structlog kwargs.

The rest of the dashboard's panels include `| json | __error__=""`
defensively, so a single broken line no longer poisons the entire
view — but the source is still worth fixing because it's wasted log
ingest cost.

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
