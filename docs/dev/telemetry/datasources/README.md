# Datasource configs

Versioned Grafana datasource configs. One JSON file per datasource. The
canonical source of truth — apply outward to whichever stack you're
targeting (Cloud now, self-hosted Grafana on the home cluster later).

## Apply

```bash
./apply.sh           # all *.json
./apply.sh loki      # substring filter on filename
```

Auth comes from `~/.config/draftforge/grafana.env` (`GRAFANA_URL`,
`GRAFANA_TOKEN`) — same file `gcx` uses.

## What the script does

For each `<name>.json`:

1. Strip every `_*` key (those are docs-only, never sent).
2. `PUT /api/datasources/uid/<uid>` with the cleaned payload.
3. On 404 → `POST /api/datasources` to create.
4. On 403 → print the UI path. Grafana Cloud marks bundled Loki / Tempo
   / Prometheus / etc. datasources read-only via API; derived fields can
   only be edited through the UI overlay. The JSON file still acts as
   the source of truth — you copy-paste from it into the UI form.

## Editing

* Add a derived field, a header, a JSON-data option → edit the file.
* Add a NEW datasource → drop a new `<name>.json` next to the existing
  one. Include `uid` (so the script can target it for updates) and
  `name`. Put any free-form documentation under `_doc` keys (top-level
  or nested) — they're stripped before send.
* Never commit secrets. The script only sends what's in the file;
  `secureJsonData` / passwords stay configured server-side and are
  preserved across PUTs as long as the field is absent from the body.

## Porting to a self-hosted Grafana

When this stack moves off Grafana Cloud, the same JSON ports cleanly:

* For **Grafana provisioning** (the `provisioning/datasources/*.yaml`
  pattern), wrap the file's content in:

  ```yaml
  apiVersion: 1
  datasources:
    - <paste the file's top-level keys here, dropping `_doc`>
  ```

  The `jsonData.derivedFields` schema is identical between cloud and
  self-hosted — no translation needed.

* For **Helm charts** (e.g. kube-prometheus-stack's
  `grafana.additionalDataSources`), same idea — pass the file content
  as a list entry.

The read-only constraint only exists on Cloud; self-hosted accepts API
writes, so `apply.sh` will work end-to-end against your home-cluster
Grafana when that exists.
