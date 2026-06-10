# ─── Stage 1: Build React SPA ───────────────────────────────────────────────
FROM node:22-alpine AS builder
WORKDIR /app

COPY package*.json ./
RUN npm ci --silent

COPY . .
# Defaults: VITE_API_URL=/api/v1  VITE_WS_URL=ws://<same-host>
# These work out of the box with nginx proxy — no build args needed.
RUN npm run build

# ─── Stage 2: Serve via nginx ────────────────────────────────────────────────
FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
