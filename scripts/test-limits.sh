#!/usr/bin/env bash
# Shared CPU/memory budget for local tests: every test-stack container (via
# compose cgroup_parent) and every host-side test runner wrapped with `wrap`
# lands in one systemd user slice, so concurrent sessions together stay under
# DF_TEST_CPUS cores and DF_TEST_MEM memory.
#
#   scripts/test-limits.sh apply        set the slice limits (idempotent)
#   scripts/test-limits.sh show         print limits and current usage
#   scripts/test-limits.sh wrap CMD...  apply, then exec CMD inside the slice
#   scripts/test-limits.sh cgroup       print the slice name, or nothing when disabled
#
# A no-op (wrap just execs CMD) in CI, with DF_TEST_LIMITS=0, or without a
# systemd user manager.
set -euo pipefail

slice=${DF_TEST_CGROUP_PARENT:-df-tests.slice}
cpus=${DF_TEST_CPUS:-16}
mem=${DF_TEST_MEM:-40G}

enabled() {
    [[ "${GITHUB_ACTIONS-}" != true && -z "${CI-}" && "${DF_TEST_LIMITS-1}" != 0 ]] &&
        command -v systemctl >/dev/null && systemctl --user show-environment >/dev/null 2>&1
}

apply() {
    enabled || return 0
    local want_quota=$((cpus * 1000000)) have_quota have_mem want_mem
    have_quota=$(systemctl --user show "$slice" -p CPUQuotaPerSecUSec --value)
    have_mem=$(systemctl --user show "$slice" -p MemoryMax --value)
    want_mem=$(numfmt --from=iec "$mem")
    # CPUQuotaPerSecUSec prints as e.g. "16s" or "1.500s"
    if [[ "$have_quota" == "$((want_quota / 1000000))s" && "$have_mem" == "$want_mem" ]]; then
        return 0
    fi
    systemctl --user set-property "$slice" "CPUQuota=$((cpus * 100))%" "MemoryMax=$mem" "MemorySwapMax=0"
}

case "${1-}" in
    apply)
        apply
        ;;
    show)
        if ! enabled; then
            echo "test limits disabled (CI, DF_TEST_LIMITS=0, or no systemd user manager)"
            exit 0
        fi
        apply
        systemctl --user show "$slice" -p CPUQuotaPerSecUSec -p MemoryMax -p MemoryCurrent -p CPUUsageNSec -p TasksCurrent
        ;;
    cgroup)
        if enabled; then
            echo "$slice"
        fi
        ;;
    wrap)
        shift
        if ! enabled; then
            exec "$@"
        fi
        apply
        exec systemd-run --user --scope --quiet --collect --slice="$slice" -- "$@"
        ;;
    *)
        echo "usage: $0 apply|show|cgroup|wrap CMD..." >&2
        exit 2
        ;;
esac
