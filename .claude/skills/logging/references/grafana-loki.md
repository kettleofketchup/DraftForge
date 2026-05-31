# Querying Loki logs with `gcx`

`gcx` is the Grafana Cloud CLI. Context `draftforge` → `kettle.grafana.net`, Loki
datasource UID `grafanacloud-logs`. Token at `~/.config/draftforge/grafana.env`.
Check context: `gcx config current-context`.

## Gotchas (read first)

- **Always pass `--agent=false`.** Under Claude Code, `gcx` auto-enables agent mode
  (detects `CLAUDECODE`), which suppresses `-o raw`/`-o table` output — queries look
  empty when they aren't. `--agent=false` restores real output. This single flag is the
  difference between "discord has zero logs" (false) and the truth.
- **`-o raw`** = original log line bodies. `query` accepts `agents,json,raw,table,wide,yaml`
  (NOT `jsonl`). `labels` accepts `agents,json,table,yaml` (NOT `raw`).
- **`--since` uses Go durations: `s`/`m`/`h` only — NOT `d`.** `--since 7d` errors with
  `unknown unit "d"`. Use `--since 168h`, or better, **`--from`/`--to`** (RFC3339) for any
  multi-day window. `--limit 0` = uncapped.
- **Label exists ≠ data exists.** Loki's label index keeps a `service_name` long after its
  logs age out. A name in `gcx logs labels` does NOT mean queryable data — confirm with a
  `query` count.
- Services: `backend`, `dtx-backend`, `discord`. Env `deployment_environment="prod"`.

## Basics

```bash
A='--agent=false'
gcx logs labels service_name $A                      # services with data (default range)
gcx logs query '{service_name="backend"}' --since 6h --limit 500 -o raw $A
gcx logs query '{service_name="backend"}' \
  --from 2026-05-30T00:00:00Z --to 2026-05-31T00:00:00Z --limit 0 -o raw $A
```

## Log format: nearly all JSON — use `| json`

Backend, celery, AND the discord bot's errors are **structlog JSON** with `level`,
`event`, `error_type` fields. Filter with the `| json` pipeline:

```bash
gcx logs query '{service_name="backend"} | json | level=`error`' --since 24h -o raw $A
gcx logs query '{service_name="discord"} | json | level=`error`' --since 24h -o raw $A
```

**Do NOT line-filter on level**: `{service_name="discord"} |= "ERROR"` returns 0, because
`ERROR` is the `level` *field* (what Grafana shows as the colored level), not text in the
body. A small minority of discord lines ARE plain text — discord.py's own
`Ignoring exception in on_interaction` banner that precedes each JSON traceback. `| json`
drops those; catch them with a separate line query:

```bash
gcx logs query '{service_name="discord"} |= `Ignoring exception`' --since 24h -o raw $A
```

## Error breakdown (triage: which errors, how many)

```bash
gcx logs query '{service_name="discord"} | json | level=`error`' \
  --from 2026-05-30T00:00:00Z --to 2026-05-31T00:00:00Z --limit 0 -o raw $A \
  | jq -r '.error_type // .event' | sort | uniq -c | sort -rn
# e.g.   SynchronousOnlyOperation   (most common)
#        HTTPException
```
(`SynchronousOnlyOperation` = a Django ORM call in async context; `HTTPException`
40060 = "Interaction has already been acknowledged" — a double-ACK race.)

## Activity / silence detection (did a service stop logging?)

```bash
gcx logs query '{service_name="discord"}' --since 168h --limit 0 -o raw $A > /tmp/d.log
head -1 /tmp/d.log   # newest (default direction=backward)
tail -1 /tmp/d.log   # oldest
wc -l /tmp/d.log
gcx logs metrics 'sum(count_over_time({service_name="discord"}[1h]))' --since 168h -o raw $A
```
A service whose label exists but whose `query` returns 0 over the window has **gone
silent** (crashed / stopped shipping) — a common root cause behind "interaction failed".

## Field extraction & request/trace correlation

```bash
# follow one Discord interaction across processes (binds in discordbot/log_context.py)
gcx logs query '{service_name="backend"} | json | interaction_id=`<id>`' --since 24h -o raw $A
# follow one web request
gcx logs query '{service_name="backend"} | json' --since 1h --limit 0 -o raw $A \
  | jq -r 'select(.["request.id"]=="<uuid>") | "\(.timestamp) \(.event)"'
# selected fields as a table
gcx logs query '{service_name="backend"} | json | system=`discord`' --since 6h -o raw $A \
  | jq -r '[.timestamp, .subsystem, .event, (.error // "")] | @tsv'
# trace_id present on ~10% sampled lines; else correlate via interaction_id
gcx logs query '{service_name="backend"} | json | event=`interaction_failed`' --since 24h -o raw $A \
  | jq -r '.trace_id // "no-trace"'
```

## Tips

- Quote LogQL string matchers with backticks inside the shell single-quoted expr
  (`level=\`error\``) to avoid nested-quote escaping.
- Pipe large pulls to a file (`> /tmp/x.log`) then `jq`/`grep` — robust against terminal
  mangling on big outputs.
- `--share-link` prints the equivalent Grafana Explore URL (to stderr) for opening in the UI.
