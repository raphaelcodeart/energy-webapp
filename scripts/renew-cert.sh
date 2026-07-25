#!/usr/bin/env bash
# Renews the Let's Encrypt certificate for this server and reloads nginx if it
# actually renewed (certbot renew is a no-op unless within 30 days of expiry,
# so this is safe to run daily via cron regardless).
#
# IMPORTANT: this project's certificate lives under ./certbot/conf, NOT the
# default /etc/letsencrypt -- so the certbot .deb package's own systemd timer
# (which only knows about /etc/letsencrypt) will NOT renew this certificate.
# This script (via cron, see setup below) is what actually keeps it current.
#
# One-time setup on a fresh server:
#   crontab -e
#   # add:
#   0 3 * * * /opt/lialenergy/scripts/renew-cert.sh >> /opt/lialenergy/certbot/renew.log 2>&1
set -euo pipefail

cd "$(dirname "$0")/.."

certbot renew \
  --config-dir ./certbot/conf \
  --work-dir ./certbot/work \
  --logs-dir ./certbot/logs \
  --webroot -w ./certbot/www \
  --deploy-hook "docker exec lial-energy-dev-nginx-1 nginx -s reload"
