FROM postgres:15-alpine

# Genera certificado autofirmado para SSL de PostgreSQL.
# El UID 70 es el usuario 'postgres' en Alpine.
RUN apk add --no-cache openssl && \
    mkdir -p /certs && \
    openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
        -keyout /certs/server.key \
        -out    /certs/server.crt \
        -subj   "/C=ES/ST=Spain/L=Local/O=GestionApp/CN=postgres" && \
    chmod 600 /certs/server.key && \
    chown 70:70 /certs/server.key /certs/server.crt

# La activación de SSL se hace SOLO desde docker-compose.yml mediante
# `command: postgres -c ssl=on -c ssl_cert_file=... -c ssl_key_file=...`.
# Esa fuente es siempre aplicada (también con volúmenes pre-existentes),
# evitando la antigua duplicidad con init-ssl.sh.
