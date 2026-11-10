FROM node:22-bookworm-slim AS build
WORKDIR /build
COPY frontend/package*.json ./
RUN --mount=type=cache,target=/root/.npm npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM caddy:2-alpine
COPY frontend/Caddyfile /etc/caddy/Caddyfile
COPY --from=build /build/dist /srv
ENV XDG_CONFIG_HOME=/tmp/caddy/config XDG_DATA_HOME=/tmp/caddy/data
USER 10001:10001
EXPOSE 3000
HEALTHCHECK --interval=15s --timeout=5s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1:3000/health
