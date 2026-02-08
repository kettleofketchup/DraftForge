# ---- Base ----
FROM node:22-alpine AS base
WORKDIR /app

# Node Alpine image already has 'node' user with UID/GID 1000
# Just ensure npm cache directory exists with correct ownership
RUN mkdir -p /home/node/.npm && \
    chown -R node:node /home/node

COPY package.json /app/
COPY package-lock.json /app/

# ---- System Deps (independent - only rebuilds when Alpine image changes) ----
# This stage installs ALL system packages needed for Playwright/browsers
# It's independent of package.json, so npm changes don't invalidate it
FROM node:22-alpine AS system-deps

# Install browsers and ALL runtime dependencies in one layer
RUN apk add --no-cache \
    # Browsers
    chromium \
    firefox \
    # Core browser dependencies
    nss \
    freetype \
    harfbuzz \
    harfbuzz-subset \
    ca-certificates \
    ttf-freefont \
    libstdc++ \
    dbus \
    # Graphics/display dependencies
    mesa-gl \
    mesa-gbm \
    libxcomposite \
    libxdamage \
    libxrandr \
    libxshmfence \
    libxxf86vm \
    pango \
    cairo \
    # Audio/accessibility
    alsa-lib \
    cups-libs \
    gtk+3.0 \
    at-spi2-core \
    # Video processing
    ffmpeg \
    # Additional chromium dependencies
    eudev-libs \
    crc32c \
    double-conversion \
    minizip \
    libxslt \
    pipewire-libs \
    libwebpdemux \
    simdutf \
    openh264 && \
    # Create chromium symlink
    ln -sf /usr/lib/chromium/chromium /usr/bin/chromium && \
    # Create ffmpeg symlink for Playwright
    mkdir -p /root/.cache/ms-playwright/ffmpeg-1011 && \
    ln -sf /usr/bin/ffmpeg /root/.cache/ms-playwright/ffmpeg-1011/ffmpeg-linux

# ---- Production Deps ----
FROM base AS deps
RUN chown -R node:node /app
USER node
RUN --mount=type=cache,target=/home/node/.npm,uid=1000,gid=1000 npm ci --omit=dev

# ---- Build Deps (includes dev deps for building) ----
FROM base AS deps-build
RUN chown -R node:node /app
USER node
RUN --mount=type=cache,target=/home/node/.npm,uid=1000,gid=1000 npm ci

# ---- Source for build ----
FROM deps-build AS source
COPY --chown=node:node . /app/

# ---- Builder ----
FROM source AS builder
USER node
# Copy docs assets from additional build context (use --build-context docs=./docs when building)
COPY --from=docs assets /app/public/assets/docs/
RUN npm run build

# ---- Runtime (production) ----
FROM deps AS runtime
LABEL org.opencontainers.image.source="https://github.com/kettleofketchup/draftforge"
WORKDIR /app
ENV PROD=false
ENV NODE_ENV="dev"
ENV RELEASE=false
ENV TEST=false
EXPOSE 3000
COPY --from=builder --chown=node:node /app/build /app/build
COPY --from=builder --chown=node:node /app/instrument.server.mjs /app/instrument.server.mjs

USER node
CMD ["npm", "run", "start"]

# ---- Dev/Test Runtime (with Playwright) ----
# Based on system-deps (has all packages pre-installed)
# Copies node_modules from deps-build
FROM system-deps AS runtime-dev
LABEL org.opencontainers.image.source="https://github.com/kettleofketchup/draftforge"
WORKDIR /app

# Ensure node user exists and has correct directories
# (node:22-alpine base already has node user, so use || true for idempotency)
RUN (addgroup -g 1000 node 2>/dev/null || true) && \
    (adduser -u 1000 -G node -s /bin/sh -D node 2>/dev/null || true) && \
    mkdir -p /home/node/.npm /home/node/.cache/ms-playwright/ffmpeg-1011 && \
    ln -sf /usr/bin/ffmpeg /home/node/.cache/ms-playwright/ffmpeg-1011/ffmpeg-linux && \
    chown -R node:node /home/node /app

# Copy node_modules from deps-build (this is the only layer affected by package.json)
COPY --from=deps-build --chown=node:node /app/node_modules /app/node_modules
COPY --chown=node:node package.json package-lock.json /app/

# Set environment variables
ENV PROD=false
ENV NODE_ENV="dev"
ENV RELEASE=false
ENV TEST=false
# Tell Playwright to use system browsers instead of downloading
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
ENV PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium
ENV PLAYWRIGHT_FIREFOX_EXECUTABLE_PATH=/usr/bin/firefox
EXPOSE 3000

# Copy and use entrypoint script
COPY --chown=node:node docker-entrypoint-frontend.sh /app/docker-entrypoint-frontend.sh
RUN chmod +x /app/docker-entrypoint-frontend.sh
USER node
CMD ["/bin/sh", "/app/docker-entrypoint-frontend.sh"]
