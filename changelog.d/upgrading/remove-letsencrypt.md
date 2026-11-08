The release stack still reads its TLS certificate from
`nginx/data/certbot/configs/live/dota.kettle.sh/` on the prod host, and still serves
`/.well-known/acme-challenge/` from `nginx/data/certbot/webroot/`. Do not delete those
directories. `just prod::certbot` is gone, so if the host still has a `certbot renew`
cron entry (installed by the old `certbot.sh`), it is now the only thing renewing that
certificate; check with `sudo crontab -l` and decide whether to keep it.
