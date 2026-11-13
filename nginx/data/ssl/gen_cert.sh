#!/usr/bin/env bash
# Self-signed cert for local dev/test stacks: slot 0 (localhost), slots N >= 1 (sN.localhost)
# and in-network Playwright (nginx). Reuses cert.key when present.
set -euo pipefail
cd "$(dirname "$0")"

san="DNS:localhost,DNS:*.localhost"
for n in 1 2 3 4 5 6 7 8 9; do san+=",DNS:s$n.localhost"; done
san+=",DNS:nginx,IP:127.0.0.1,IP:::1"

[ -f cert.key ] || openssl genrsa -out cert.key 2048
openssl req -new -key cert.key -subj "/CN=localhost" -addext "subjectAltName=$san" -out cert.csr
openssl x509 -req -in cert.csr -signkey cert.key -sha256 -days 825 -copy_extensions copy \
  -extfile <(printf 'basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\n') \
  -out cert.crt
for h in localhost s1.localhost s9.localhost nginx; do
  openssl verify -CAfile cert.crt -partial_chain -verify_hostname "$h" cert.crt >/dev/null
done
openssl x509 -in cert.crt -noout -ext subjectAltName
