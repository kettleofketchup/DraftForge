# ---- Base ----
FROM node:22-alpine AS base
WORKDIR /app
RUN mkdir -p /root/.npm /root/.cache/Cypress

COPY package.json /app/
COPY package-lock.json /app/

# ---- Production Deps ----
FROM base AS deps
RUN --mount=type=cache,target=/root/.npm npm ci --omit=dev

# ---- Build Deps (includes dev deps for building, but no Cypress) ----
FROM base AS deps-build
RUN --mount=type=cache,target=/root/.npm npm ci

# ---- Source for build ----
FROM deps-build AS source
COPY . /app/

# ---- Builder ----
FROM source AS builder
RUN npm run build

# ---- Runtime (production) ----
FROM deps AS runtime
LABEL org.opencontainers.image.source="https://github.com/kettleofketchup/dota_tournament"
WORKDIR /app
ENV PROD=false
ENV NODE_ENV="dev"
ENV RELEASE=false
ENV TEST=false
EXPOSE 3000
COPY --from=builder /app/build /app/build
CMD ["npm", "run", "start"]

# ---- Dev/Test Deps (with Cypress) ----
FROM deps-build AS deps-dev
ENV CYPRESS_CACHE_FOLDER=/root/.cache/Cypress

# Install Cypress binaries and copy to permanent location
RUN --mount=type=cache,target=/tmp/cypress-cache \
    CYPRESS_CACHE_FOLDER=/tmp/cypress-cache npx cypress install && \
    mkdir -p /root/.cache/Cypress && \
    cp -r /tmp/cypress-cache/* /root/.cache/Cypress/ 2>/dev/null || true

# Verify Cypress installation
RUN npx cypress --version

# ---- Runtime (dev) ----
FROM deps-dev AS runtime-dev
LABEL org.opencontainers.image.source="https://github.com/kettleofketchup/dota_tournament"
WORKDIR /app
ENV PROD=false
ENV NODE_ENV="dev"
ENV RELEASE=false
ENV TEST=false
ENV CYPRESS_CACHE_FOLDER=/root/.cache/Cypress
EXPOSE 3000
CMD ["npx", "react-router", "dev" ,"--port", "3000", "--host", "0.0.0.0"]
