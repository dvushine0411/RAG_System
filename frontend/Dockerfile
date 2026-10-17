# frontend/Dockerfile — React + Vite → Nginx
# Multi-stage build: stage 1 build, stage 2 serve

# ── Stage 1: Build React/Vite App ─────────────────────────────────
FROM node:20-alpine AS builder
WORKDIR /app

# Cài dependencies trước (tận dụng Docker layer cache)
COPY package*.json ./
RUN npm ci

# Copy source và build production bundle
COPY . .
RUN npm run build
# Output: /app/dist

# ── Stage 2: Serve với Nginx (Alpine) ─────────────────────────────
FROM nginx:1.27-alpine AS production

# Copy build artifacts từ stage 1
COPY --from=builder /app/dist /usr/share/nginx/html

# Nginx config: SPA fallback, proxy /api → api:3000, unbuffered SSE cho /api/v1/query/stream
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
