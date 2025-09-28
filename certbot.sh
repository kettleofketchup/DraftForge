#!/bin/bash
# filepath: /home/kettle/git_repos/website/scripts/setup-ssl.sh

set -e  # Exit on any error

# Configuration
DOMAIN="dota.kettle.sh"
WWW_DOMAIN="www.dota.kettle.sh"
WEBROOT_PATH="/home/website/website/nginx/data/certbot/webroot"
WORK_DIR="/home/website/website/nginx/data/certbot/work"
CONFIG_DIR="/home/website/website/nginx/data/certbot/configs"
LOGS_DIR="/home/website/website/nginx/data/certbot/logs"

echo "Starting SSL certificate setup for ${DOMAIN}..."

# Create necessary directories
echo "Creating certbot directories..."
sudo mkdir -p "${WEBROOT_PATH}"
sudo mkdir -p "${WORK_DIR}"
sudo mkdir -p "${CONFIG_DIR}"
sudo mkdir -p "${LOGS_DIR}"

# Set proper permissions
echo "Setting directory permissions..."
sudo chown -R www-data:www-data "${WEBROOT_PATH}"
sudo chmod -R 755 "${WEBROOT_PATH}"

# Check if nginx is running (needed for webroot validation)
echo "Checking nginx status..."
if ! systemctl is-active --quiet nginx; then
    echo "Starting nginx..."
    sudo systemctl start nginx
fi

# Request certificate
echo "Requesting SSL certificate for ${DOMAIN} and ${WWW_DOMAIN}..."
sudo certbot certonly \
    --register-unsafely-without-email \
    --agree-tos \
    --force-renewal \
    --webroot \
    --webroot-path "${WEBROOT_PATH}" \
    --work-dir "${WORK_DIR}" \
    --config-dir "${CONFIG_DIR}" \
    --logs-dir "${LOGS_DIR}" \
    -d "${DOMAIN}" \
    -d "${WWW_DOMAIN}"

if [ $? -eq 0 ]; then
    echo "SSL certificate successfully obtained!"
    echo "Certificate location: ${CONFIG_DIR}/live/${DOMAIN}/"

    # Reload nginx to use the new certificate
    echo "Reloading nginx..."
    sudo systemctl reload nginx

    echo "SSL setup complete!"
else
    echo "Failed to obtain SSL certificate!"
    exit 1
fi

# Optional: Set up auto-renewal
echo "Setting up auto-renewal..."
sudo crontab -l 2>/dev/null | grep -v "certbot renew" | sudo crontab -
(sudo crontab -l 2>/dev/null; echo "0 12 * * * certbot renew --quiet --work-dir ${WORK_DIR} --config-dir ${CONFIG_DIR} --logs-dir ${LOGS_DIR} && systemctl reload nginx") | sudo crontab -

echo "Auto-renewal cron job added (runs daily at 12:00 PM)"
echo "Setup complete!"
