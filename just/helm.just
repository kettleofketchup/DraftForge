# Helm chart commands (helm/). Same tool versions as .github/workflows/helm-chart.yml.
# Helm must be v3.19.4, the version the ArgoCD v3.3.4 repo-server renders with;
# the helm on PATH may be Helm 4, so HELM is the mise-installed v3.19.4 binary.

root := source_directory() / ".."
chart := root / "helm"

HELM_VERSION := "3.19.4"
HELM_UNITTEST_VERSION := "v1.2.1"
# just evaluates this for every recipe in every module, so a missing mise Helm must
# not break unrelated recipes: HELM then names a command that fails with the fix.
export HELM := shell('d=$(mise where "helm@$1" 2>/dev/null) && echo "$d/linux-amd64/helm" || echo "helm-$1-missing-run-mise-install-helm@$1"', HELM_VERSION)

preview_values := "-f " + chart / "values-preview.yaml" + " -f " + chart / "tests/fixtures/preview-appset-values.yaml" + " --namespace draftforge-pr-1"

# Install the pinned helm-unittest plugin into the v3.19.4 Helm
[group('helm')]
plugins:
    #!/usr/bin/env bash
    set -euo pipefail
    if "$HELM" plugin list | awk 'NR>1 {print $1, $2}' | grep -qx "unittest {{ trim_start_match(HELM_UNITTEST_VERSION, 'v') }}"; then
        echo "helm-unittest {{HELM_UNITTEST_VERSION}} already installed"
        exit 0
    fi
    "$HELM" plugin install https://github.com/helm-unittest/helm-unittest.git --version {{HELM_UNITTEST_VERSION}}

# Lint the chart with default values and with the preview profile
[group('helm')]
lint:
    #!/usr/bin/env bash
    set -euo pipefail
    "$HELM" lint --strict {{chart}}
    "$HELM" lint --strict {{chart}} {{preview_values}}

# Render the chart: profile is default or preview
[group('helm')]
template profile="default":
    #!/usr/bin/env bash
    set -euo pipefail
    case "{{profile}}" in
        default) "$HELM" template draftforge {{chart}} ;;
        preview) "$HELM" template draftforge-pr-1 {{chart}} {{preview_values}} ;;
        *) echo "unknown profile '{{profile}}' (use default or preview)" >&2; exit 2 ;;
    esac

# Chart unit tests, budget, render-safety, kubeconform and the preview script tests
[group('helm')]
test:
    #!/usr/bin/env bash
    set -euo pipefail
    cd {{root}}
    if ! "$HELM" plugin list | awk 'NR>1 {print $1}' | grep -qx unittest; then
        echo "FAIL: helm-unittest is not installed for $HELM; run: just helm::plugins" >&2
        exit 1
    fi
    "$HELM" unittest {{chart}}
    render=$(mktemp -d)
    trap 'rm -rf "$render"' EXIT
    just helm::template default > "$render/default.yaml"
    just helm::template preview > "$render/preview.yaml"
    yq -o=json ea '[.]' "$render/preview.yaml" | python3 -I scripts/helm_budget_check.py
    scripts/helm_render_safety.sh {{chart}}
    cache="${KUBECONFORM_CACHE:-$HOME/.cache/kubeconform}"
    mkdir -p "$cache"
    for profile in default preview; do
        kubeconform -strict -ignore-missing-schemas -summary -cache "$cache" "$render/$profile.yaml"
    done
    PYTHONDONTWRITEBYTECODE=1 python3 -I -m unittest discover -s scripts/preview_tests -t . -v
