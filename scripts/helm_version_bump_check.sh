#!/usr/bin/env bash
# Chart version-bump check.
#
#   scripts/helm_version_bump_check.sh <base_sha>
#
# Run from inside the repository. Exits 1 if anything under helm/ other than
# helm/tests/ and helm/README.md differs between <base_sha> and HEAD while
# helm/Chart.yaml `version` is unchanged.
# A base without helm/Chart.yaml counts as bumped (the chart is new).
# Each chart version names one chart tag (chart-v<version>), so every rendered
# helm/ change needs its own version.
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: $0 <base_sha>" >&2
  exit 2
fi
base=$1
YQ=${YQ:-yq}

if ! git rev-parse --quiet --verify "${base}^{commit}" >/dev/null; then
  echo "FAIL: base $base is not a commit in this repository" >&2
  exit 2
fi

# helm/tests/ is .helmignored and README.md never renders: neither needs a bump.
if git diff --quiet "$base" HEAD -- helm/ ':(exclude)helm/tests/' ':(exclude)helm/README.md'; then
  echo "OK: rendered helm/ unchanged since $base"
  exit 0
fi

if ! base_chart=$(git show "$base:helm/Chart.yaml" 2>/dev/null); then
  echo "OK: helm/Chart.yaml is new since $base"
  exit 0
fi

base_version=$("$YQ" '.version' <<<"$base_chart")
head_version=$(git show HEAD:helm/Chart.yaml | "$YQ" '.version')

if [[ $base_version == "$head_version" ]]; then
  echo "FAIL: helm/ changed but Chart.yaml version was not bumped (still $head_version)" >&2
  exit 1
fi
echo "OK: chart version $base_version -> $head_version"
