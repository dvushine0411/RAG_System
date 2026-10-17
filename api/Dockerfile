# api/Dockerfile — Node.js Fastify API Gateway
# Multi-stage build: deps → build TypeScript → production runtime

# ── Stage 1: Install Dependencies ─────────────────────────────────
FROM node:20-alpine AS deps
WORKDIR /app

# Copy manifest files để tận dụng Docker layer cache
COPY package*.json ./
RUN npm ci --frozen-lockfile

# ── Stage 2: Build TypeScript ──────────────────────────────────────
FROM node:20-alpine AS builder
WORKDIR /app

COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build
# Output: /app/dist

# ── Stage 3: Production Runtime ───────────────────────────────────
FROM node:20-alpine AS production
WORKDIR /app

ENV NODE_ENV=production

# Chỉ copy những gì cần thiết cho production
COPY --from=deps /app/node_modules ./node_modules
COPY --from=builder /app/dist ./dist
COPY package*.json ./

# Chạy với user non-root (bảo mật)
RUN addgroup -S appgroup && adduser -S appuser -G appgroup
USER appuser

EXPOSE 3000

# Healthcheck endpoint
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -qO- http://127.0.0.1:3000/health || exit 1

CMD ["node", "dist/server.js"]
