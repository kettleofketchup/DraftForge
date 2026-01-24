FROM jonasal/nginx-certbot:5.4.1-nginx1.27.4 AS runtime
LABEL org.opencontainers.image.source="https://github.com/kettleofketchup/draftforge"

RUN mkdir -p /etc/letsencrypt/live/dota.kettle.sh/
ENV DOMAIN=localhost
ENV FRONTEND_HOST=localhost
ENV FRONTEND_PORT=3000
ENV BACKEND_HOST=localhost
ENV BACKEND_PORT=8000
COPY entrypoint.sh /entrypoint.sh
# Copy template and script
COPY default.template.conf /etc/nginx/templates/default.template.conf

# Use custom entrypoint
ENTRYPOINT ["/entrypoint.sh"]
