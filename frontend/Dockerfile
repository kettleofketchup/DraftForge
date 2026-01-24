# ---- Base ----
FROM node:22-alpine AS base
WORKDIR /app

# Node Alpine image already has 'node' user with UID/GID 1000
# Just ensure npm cache directory exists with correct ownership
RUN mkdir -p /home/node/.npm && \
    chown -R node:node /home/node

COPY package.json /app/
COPY package-lock.json /app/

# ---- Browser Stage (fully independent - only rebuilds when node:22-alpine changes) ----
FROM node:22-alpine AS browsers

# Install system browsers and dependencies (fast, from apk cache)
RUN apk add --no-cache \
    chromium \
    firefox \
    nss \
    freetype \
    harfbuzz \
    ca-certificates \
    ttf-freefont \
    libstdc++ \
    dbus

# Set up Cypress cache
ENV CYPRESS_CACHE_FOLDER=/browsers/cypress
RUN mkdir -p /browsers/cypress && \
    npm install cypress@latest --prefix /tmp/cy && \
    /tmp/cy/node_modules/.bin/cypress install && \
    rm -rf /tmp/cy

# Playwright will use system browsers - no download needed
# Just create the directory structure
RUN mkdir -p /browsers/playwright

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
USER node
CMD ["npm", "run", "start"]

# ---- Dev/Test Runtime (with Cypress and Playwright) ----
FROM deps-build AS runtime-dev
LABEL org.opencontainers.image.source="https://github.com/kettleofketchup/draftforge"
WORKDIR /app

# Copy system browsers and deps from browsers stage
COPY --from=browsers /usr/bin/chromium-browser /usr/bin/chromium-browser
COPY --from=browsers /usr/bin/firefox /usr/bin/firefox
COPY --from=browsers /usr/lib/chromium /usr/lib/chromium
COPY --from=browsers /usr/lib/firefox /usr/lib/firefox
COPY --from=browsers /usr/share/fonts /usr/share/fonts

# Install browser runtime dependencies
USER root
RUN apk add --no-cache \
    nss \
    freetype \
    harfbuzz \
    ca-certificates \
    ttf-freefont \
    libstdc++ \
    dbus \
    mesa-gl \
    libxcomposite \
    libxdamage \
    libxrandr \
    libxshmfence \
    libxxf86vm \
    pango \
    cairo \
    alsa-lib \
    cups-libs \
    gtk+3.0 \
    at-spi2-core

# Copy Cypress cache from browsers stage
COPY --from=browsers --chown=node:node /browsers/cypress /home/node/.cache/Cypress

# Set environment variables
ENV PROD=false
ENV NODE_ENV="dev"
ENV RELEASE=false
ENV TEST=false
ENV CYPRESS_CACHE_FOLDER=/home/node/.cache/Cypress
# Tell Playwright to use system browsers instead of downloading
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
ENV PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium-browser
ENV PLAYWRIGHT_FIREFOX_EXECUTABLE_PATH=/usr/bin/firefox
EXPOSE 3000

# Verify Cypress installation
USER node
RUN npx cypress --version

# Copy and use entrypoint script
COPY --chown=node:node docker-entrypoint-frontend.sh /app/docker-entrypoint-frontend.sh
USER root
RUN chmod +x /app/docker-entrypoint-frontend.sh
USER node
CMD ["/bin/sh", "/app/docker-entrypoint-frontend.sh"]
