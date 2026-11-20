#!/bin/sh
set -e

# Create config from template
envsubst '${NODE_ENV} ${RELEASE} ${DEBUG} ${DOMAIN} ${FRONTEND_HOST} ${FRONTEND_PORT} ${BACKEND_HOST} ${BACKEND_PORT}' < /etc/nginx/templates/default.template.conf > /etc/nginx/conf.d/default.conf

# nginx resolves upstream hostnames once, at startup. When a frontend or backend
# container is recreated or restarted it gets a new IP and nginx keeps proxying to
# the old one. Reload (graceful) whenever either name resolves to something new.
snapshot() {
    out=""
    for host in "$@"; do
        out="$out $(getent hosts "$host")" || return 1
    done
    echo "$out"
}

watch_upstreams() {
    last=$(snapshot "$@" || true)
    while sleep "${UPSTREAM_WATCH_INTERVAL:-5}"; do
        now=$(snapshot "$@") || continue
        if [ "$now" != "$last" ] && nginx -s reload; then
            last=$now
        fi
    done
}

watch_upstreams frontend backend &

# Run Nginx
exec nginx -g 'daemon off;'
