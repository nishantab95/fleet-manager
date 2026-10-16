# syntax=docker/dockerfile:1.7
FROM node:24.9.0-alpine3.22 AS dependencies
WORKDIR /app
COPY apps/marketing/package.json apps/marketing/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci --no-audit --no-fund

FROM node:24.9.0-alpine3.22 AS builder
ENV NEXT_TELEMETRY_DISABLED=1
WORKDIR /app
COPY --from=dependencies /app/node_modules ./node_modules
COPY apps/marketing/ ./
RUN npm run build

FROM node:24.9.0-alpine3.22 AS runtime
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0 \
    PORT=3001 \
    FLEET_MARKETING_LEAD_DIR=/var/lib/fleet-ai/leads
WORKDIR /app
RUN addgroup --system --gid 10001 fleet \
    && adduser --system --uid 10001 --ingroup fleet fleet
COPY --from=builder --chown=fleet:fleet /app/.next/standalone ./
COPY --from=builder --chown=fleet:fleet /app/.next/static ./.next/static
COPY --from=builder --chown=fleet:fleet /app/public ./public
USER fleet
EXPOSE 3001
HEALTHCHECK --interval=20s --timeout=5s --start-period=20s --retries=5 \
  CMD ["wget", "--quiet", "--tries=1", "--spider", "http://127.0.0.1:3001/health"]
CMD ["node", "server.js"]
