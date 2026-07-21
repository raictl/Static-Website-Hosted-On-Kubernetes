# Unprivileged Nginx image: runs as a non-root user by default (UID 101),
# listens on 8080 instead of 80 so it doesn't need root to bind the port.
FROM nginxinc/nginx-unprivileged:1.27-alpine

COPY index.html /usr/share/nginx/html/index.html

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s CMD wget -qO- http://localhost:8080/ || exit 1
