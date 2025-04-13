#!/bin/bash
openssl genrsa -des3 -out rootCA.key 2048
openssl req -x509 -new -nodes -key rootCA.key -sha256 -days 99999 -out rootCert.pem
openssl genrsa -out cert.key 2048
openssl req -new -key cert.key -out cert.csr
openssl x509 -req -in cert.csr -CA rootCert.pem -CAkey rootCA.key -CAcreateserial -out cert.crt -days 730 -sha256 -extfile openssl.cnf
openssl verify -CAfile rootCert.pem -verify_hostname localhost cert.crt
