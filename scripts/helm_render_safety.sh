#!/usr/bin/env bash
# Render-safety check for a chart directory that ArgoCD renders directly.
#
#   scripts/helm_render_safety.sh <chart-dir>
#
# Fails (exit 1, one FAIL line per violation) if the chart could make the
# repo-server fetch or read anything beyond plain Helm templates: Chart.yaml
# dependencies, a charts/ directory, .argocd-source* / kustomization files,
# symlinks, or a .gitmodules / gitlink anywhere in the containing repository.
# Outside a git repository it fails closed, since the last two cannot be checked.
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: $0 <chart-dir>" >&2
  exit 2
fi
dir=$1
YQ=${YQ:-yq}
failed=0
fail() { echo "FAIL: $*" >&2; failed=1; }

if [[ ! -d $dir || ! -f $dir/Chart.yaml ]]; then
  echo "FAIL: $dir is not a chart directory (no Chart.yaml)" >&2
  exit 1
fi

if [[ $("$YQ" 'has("dependencies")' "$dir/Chart.yaml") != "false" ]]; then
  fail "$dir/Chart.yaml declares dependencies"
fi

if [[ -e $dir/charts || -L $dir/charts ]]; then
  fail "$dir/charts/ exists"
fi

found=$(find "$dir" \( -name '.argocd-source*' -o -name 'kustomization.y*ml' \
  -o -name Kustomization -o -type l \) -print)
if [[ -n $found ]]; then
  while IFS= read -r path; do
    fail "forbidden file or symlink: $path"
  done <<<"$found"
fi

if ! top=$(git -C "$dir" rev-parse --show-toplevel 2>/dev/null); then
  echo "FAIL: $dir is not inside a git repository" >&2
  exit 1
fi

if [[ -e $top/.gitmodules ]] || git -C "$top" cat-file -e HEAD:.gitmodules 2>/dev/null; then
  fail "$top has a .gitmodules"
fi

if ! tree=$(git -C "$top" ls-tree -r HEAD); then
  fail "cannot list HEAD of $top"
fi
gitlinks=$( { awk '$1=="160000"' <<<"$tree"; git -C "$top" ls-files -s | awk '$1=="160000"'; } )
if [[ -n $gitlinks ]]; then
  while IFS= read -r entry; do
    fail "gitlink (mode 160000) in $top: $entry"
  done <<<"$gitlinks"
fi

if [[ $failed -ne 0 ]]; then
  exit 1
fi
echo "OK: $dir is render-safe"
