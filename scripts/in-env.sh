#!/usr/bin/env bash
# Usage: scripts/in-env.sh <env> <dir> <command> [args...]
#
# Exports docker/.env.<env> (dev, test, prod or release; "-" for none), changes
# to <dir> relative to the repo root, then execs the command. Values in the env
# file override the caller's environment.
set -euo pipefail

if [[ $# -lt 3 ]]; then
    echo "usage: $0 <env|-> <dir> <command> [args...]" >&2
    exit 2
fi

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
env_name=$1
dir=$2
shift 2

if [[ "$env_name" != "-" ]]; then
    env_file="$root/docker/.env.$env_name"
    if [[ ! -f "$env_file" ]]; then
        echo "$0: no env file $env_file" >&2
        exit 2
    fi
    set -a
    # shellcheck source=/dev/null
    . "$env_file"
    set +a
fi

cd "$root/$dir"
exec "$@"
