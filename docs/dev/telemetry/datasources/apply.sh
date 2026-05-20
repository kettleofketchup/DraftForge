#!/usr/bin/env bash
#
# Push the versioned datasource configs in this directory to the current
# Grafana Cloud stack. Reads auth from ~/.config/draftforge/grafana.env
# (GRAFANA_URL + GRAFANA_TOKEN — same file `gcx` uses).
#
# Adding a new datasource? Drop a `<name>.json` file beside this script
# (no `_doc` or `_*` keys are sent — they're filtered out before POST/PUT).
# The "uid" lives server-side and is matched by the file's `name`.
#
# Local-Grafana port note: when you move to a self-hosted Grafana on the
# home cluster, copy each json's `jsonData` block into a YAML provisioning
# file under `provisioning/datasources/` — schema is identical, only the
# wrapper format differs. See the `_doc` arrays in each file for details.
#
# Usage:
#   ./apply.sh           # apply all *.json in this dir
#   ./apply.sh loki      # apply just grafanacloud-loki.json (substring match)

set -euo pipefail

ENV_FILE="${HOME}/.config/draftforge/grafana.env"
if [[ ! -f "$ENV_FILE" ]]; then
    echo "error: $ENV_FILE not found. Create it with GRAFANA_URL and GRAFANA_TOKEN." >&2
    exit 1
fi
set -a; source "$ENV_FILE"; set +a

if [[ -z "${GRAFANA_URL:-}" || -z "${GRAFANA_TOKEN:-}" ]]; then
    echo "error: GRAFANA_URL or GRAFANA_TOKEN not set in $ENV_FILE" >&2
    exit 1
fi

cd "$(dirname "$0")"
filter="${1:-}"

shopt -s nullglob
for src in *.json; do
    [[ -n "$filter" && "$src" != *"$filter"* ]] && continue
    name=$(python3 -c "import json,sys; print(json.load(open('$src'))['name'])")

    echo "==> $src ($name)"

    # Drop documentation-only `_*` keys (recursive) before sending.
    payload=$(python3 - "$src" <<'PY'
import json, sys
def strip_docs(o):
    if isinstance(o, dict):
        return {k: strip_docs(v) for k, v in o.items() if not k.startswith("_")}
    if isinstance(o, list):
        return [strip_docs(x) for x in o]
    return o
print(json.dumps(strip_docs(json.load(open(sys.argv[1])))))
PY
)

    # Try to update by UID first; if 404 then POST as create.
    uid=$(python3 -c "import json,sys; d=json.load(open('$src')); print(d.get('uid',''))")
    if [[ -n "$uid" ]]; then
        code=$(curl -sS -o /tmp/_ds_resp.json -w "%{http_code}" \
            -X PUT \
            -H "Authorization: Bearer $GRAFANA_TOKEN" \
            -H "Content-Type: application/json" \
            -d "$payload" \
            "$GRAFANA_URL/api/datasources/uid/$uid")
        case "$code" in
            200|201) echo "    updated (HTTP $code)" ;;
            404)
                echo "    not found (HTTP 404); creating"
                code=$(curl -sS -o /tmp/_ds_resp.json -w "%{http_code}" \
                    -X POST \
                    -H "Authorization: Bearer $GRAFANA_TOKEN" \
                    -H "Content-Type: application/json" \
                    -d "$payload" \
                    "$GRAFANA_URL/api/datasources")
                echo "    create result: HTTP $code"
                ;;
            403)
                # Grafana Cloud marks the bundled Loki/Tempo/etc. datasources
                # read-only via API. Derived fields can still be edited via
                # the UI overlay — print the path so the user can apply
                # manually. The JSON file stays as the source of truth for
                # when this stack migrates to a self-hosted Grafana that
                # accepts API writes (or for provisioning into k8s).
                echo "    READ-ONLY datasource (HTTP 403). Apply via UI:"
                echo "      $GRAFANA_URL/connections/datasources/edit/$uid"
                echo "    Scroll to 'Derived fields' and add the entries from $src."
                ;;
            *)
                echo "    FAILED (HTTP $code):" >&2
                cat /tmp/_ds_resp.json >&2 ; echo >&2
                exit 1
                ;;
        esac
    fi
done
