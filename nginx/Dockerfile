FROM nginx:1.27-alpine

# Genera certificado autofirmado en tiempo de build.
# En producción con dominio real: reemplazar por certs de Let's Encrypt
# montados en /etc/nginx/certs/ como volumen externo.
RUN apk add --no-cache openssl && \
    mkdir -p /etc/nginx/certs && \
    openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
        -keyout /etc/nginx/certs/server.key \
        -out    /etc/nginx/certs/server.crt \
        -subj   "/C=ES/ST=Spain/L=Local/O=GestionApp/CN=localhost" \
        -addext "subjectAltName=IP:127.0.0.1,DNS:localhost" && \
    chmod 600 /etc/nginx/certs/server.key

COPY nginx.conf /etc/nginx/nginx.conf

EXPOSE 80 443
