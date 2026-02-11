#!/usr/bin/env bash
# Outputs SHA256 hash of files that determine a Docker image's installed dependencies.
# Usage: ./scripts/hash-docker-image.sh <frontend|backend|nginx>
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

case "${1:-}" in
  frontend)
    cat frontend/Dockerfile frontend/package-lock.json | sha256sum | cut -d' ' -f1
    ;;
  backend)
    cat backend/Dockerfile poetry.lock | sha256sum | cut -d' ' -f1
    ;;
  nginx)
    cat nginx/Dockerfile nginx/entrypoint.sh nginx/default.template.conf | sha256sum | cut -d' ' -f1
    ;;
  *)
    echo "Usage: $0 <frontend|backend|nginx>" >&2
    exit 1
    ;;
esac
