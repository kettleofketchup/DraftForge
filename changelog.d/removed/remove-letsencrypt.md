- **Let's Encrypt tooling.** Removed `init-letsencrypt.sh`, `certbot.sh`, the
  `just prod::certbot` / `inv prod.certbot` task, the unused `certbot-nginx` Python
  dependency, the unused `nginx/nginx_http.template.conf`, and the jonasal/nginx-certbot
  `CERTBOT_*` settings in `docker/.env.release` (the custom nginx entrypoint never ran
  certbot). Dev, test and `docker-compose.prod.yaml` no longer mount `nginx/data/certbot/*`;
  the release stack drops only the unused `work/` and `logs/` mounts. Closes #325.
