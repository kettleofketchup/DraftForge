#!/bin/sh
set -e

# Create config from template
envsubst '${NODE_ENV} ${RELEASE} ${DEBUG} ${DOMAIN} ${FRONTEND_HOST} ${FRONTEND_PORT} ${BACKEND_HOST} ${BACKEND_PORT}' < /etc/nginx/templates/default.template.conf > /etc/nginx/conf.d/default.conf
# Run Nginx
exec nginx -g 'daemon off;'
