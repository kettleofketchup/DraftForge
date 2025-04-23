FROM jonasal/nginx-certbot:5.4.1-nginx1.27.4


# Copy template and script
COPY default.template.conf /etc/nginx/templates/default.template.conf
COPY entrypoint.sh /entrypoint.sh
RUN mkdir -P /etc/letsencrypt/live/dtxdota.com/
RUN chown -R /etc/letsencrypt/live/dtxdota.com/
ENV DOMAIN=localhost
ENV FRONTEND_HOST=localhost
ENV FRONTEND_PORT=3000
ENV BACKEND_HOST=localhost
ENV BACKEND_PORT=8000

# Use custom entrypoint
ENTRYPOINT ["/entrypoint.sh"]
