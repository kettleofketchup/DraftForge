#!/bin/bash

if ! docker compose version >/dev/null 2>&1; then
  echo 'Error: docker compose is not installed.' >&2
  exit 1
fi

root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
compose=(docker compose --project-directory "$root" -f "$root/docker/docker-compose.release.yaml")

domains=(dota.kettle.sh www.dota.kettle.sh)
domain="${domains[0]}"
rsa_key_size=4096
data_path="$root/nginx/data/certbot"
email="" # Adding a valid address is strongly recommended
staging=0 # Set to 1 if you're testing your setup to avoid hitting request limits

if [ -d "$data_path/configs/live/$domain" ]; then
  read -r -p "Existing data found for $domain. Continue and replace existing certificate? (y/N) " decision
  if [ "$decision" != "Y" ] && [ "$decision" != "y" ]; then
    exit
  fi
fi


echo "### Creating dummy certificate for $domain ..."
path="/etc/letsencrypt/live/$domain"
mkdir -p "$data_path/configs/live/$domain"
"${compose[@]}" run --rm --entrypoint "\
  openssl req -x509 -nodes -newkey rsa:$rsa_key_size -days 1\
    -keyout '$path/privkey.pem' \
    -out '$path/fullchain.pem' \
    -subj '/CN=localhost'" certbot
echo


echo "### Starting nginx ..."
"${compose[@]}" up --force-recreate -d nginx
echo

echo "### Deleting dummy certificate for $domain ..."
"${compose[@]}" run --rm --entrypoint "\
  rm -Rf /etc/letsencrypt/live/$domain && \
  rm -Rf /etc/letsencrypt/archive/$domain && \
  rm -Rf /etc/letsencrypt/renewal/$domain.conf" certbot
echo


echo "### Requesting Let's Encrypt certificate for $domain ..."
#Join $domains to -d args
domain_args=""
for d in "${domains[@]}"; do
  domain_args="$domain_args -d $d"
done

# Select appropriate email arg
case "$email" in
  "") email_arg="--register-unsafely-without-email" ;;
  *) email_arg="--email $email" ;;
esac

# Enable staging mode if needed
staging_arg=""
if [ "$staging" != "0" ]; then staging_arg="--staging"; fi

"${compose[@]}" run --rm --entrypoint "\
  certbot certonly --webroot -w /var/www/certbot \
    $staging_arg \
    $email_arg \
    $domain_args \
    --rsa-key-size $rsa_key_size \
    --agree-tos \
    --force-renewal" certbot
echo

echo "### Reloading nginx ..."
"${compose[@]}" exec nginx nginx -s reload
