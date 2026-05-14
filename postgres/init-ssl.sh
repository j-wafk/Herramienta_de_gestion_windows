#!/bin/sh
# DESUSO — La activación de SSL ahora se hace exclusivamente desde
# docker-compose.yml (`command: postgres -c ssl=on -c ssl_cert_file=...`).
#
# Mantener una sola fuente evita configuración duplicada y comportamientos
# divergentes entre volúmenes nuevos y pre-existentes (los scripts de
# /docker-entrypoint-initdb.d/ solo se ejecutan en el primer initdb).
#
# Este archivo se conserva como referencia histórica y NO se copia ya
# dentro de la imagen (ver postgres/Dockerfile).
exit 0
