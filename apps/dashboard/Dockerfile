# Build context is the monorepo root (see docker-compose.dev.yml) because pnpm
# workspaces need the root package.json/pnpm-workspace.yaml/lockfile.

FROM node:22-slim AS base
ENV PNPM_HOME=/pnpm
ENV PATH="$PNPM_HOME:$PATH"
RUN corepack enable

FROM base AS deps
WORKDIR /repo
COPY package.json pnpm-workspace.yaml ./
COPY apps/dashboard/package.json apps/dashboard/package.json
RUN pnpm install --frozen-lockfile=false

FROM base AS builder
WORKDIR /repo
COPY --from=deps /repo/node_modules ./node_modules
COPY --from=deps /repo/apps/dashboard/node_modules ./apps/dashboard/node_modules
COPY package.json pnpm-workspace.yaml ./
COPY apps/dashboard apps/dashboard
ENV NEXT_TELEMETRY_DISABLED=1
RUN pnpm --filter dashboard build

FROM base AS runtime
# node:22-slim already ships a non-root "node" user at uid/gid 1000 -- reuse it
# instead of creating a colliding "app" user.
WORKDIR /app

COPY --from=builder --chown=node:node /repo/apps/dashboard/.next/standalone ./
COPY --from=builder --chown=node:node /repo/apps/dashboard/.next/static ./apps/dashboard/.next/static
COPY --from=builder --chown=node:node /repo/apps/dashboard/public ./apps/dashboard/public

USER node
ENV NODE_ENV=production
EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD node -e "fetch('http://localhost:3000/login').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"

CMD ["node", "apps/dashboard/server.js"]
