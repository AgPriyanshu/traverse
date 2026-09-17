# syntax=docker/dockerfile:1.9
#
# Build context is the REPO ROOT so this image can be built from the same
# compose file as api/.
ARG NODE_VERSION=22

FROM node:${NODE_VERSION}-alpine AS builder
ENV PNPM_HOME=/pnpm \
    PATH=/pnpm:$PATH \
    CI=1
RUN corepack enable

WORKDIR /src
COPY web/package.json web/pnpm-lock.yaml ./
RUN --mount=type=cache,target=/pnpm/store \
    pnpm config set store-dir /pnpm/store && pnpm install --frozen-lockfile

COPY web/ ./
RUN pnpm build


FROM nginx:1.27-alpine AS runtime
RUN rm -f /etc/nginx/conf.d/default.conf
COPY web/nginx.conf /etc/nginx/conf.d/traverse.conf
COPY --from=builder /src/dist /usr/share/nginx/html

EXPOSE 80
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=5 \
    CMD wget -qO- http://127.0.0.1/ >/dev/null || exit 1
