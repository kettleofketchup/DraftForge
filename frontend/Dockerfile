# ---- Base ----
FROM node:22-alpine AS base
WORKDIR /app
RUN mkdir -p /root/.npm /root/.cache/Cypress

COPY package.json /app/
COPY package-lock.json /app/

# ---- Production Deps ----
FROM base AS deps
RUN --mount=type=cache,target=/root/.npm npm ci --omit=dev

# ---- Dev/Test ----
FROM deps AS deps-dev
RUN --mount=type=cache,target=/root/.npm \
    npm ci --include=dev --ignore-scripts


ENV CYPRESS_CACHE_FOLDER=/root/.cache/Cypress

    # Then install Cypress binaries (cached separately)
RUN --mount=type=cache,target=/root/.cache/Cypress \
    npx cypress install

# ---- Source  ----
    # Intermediate stage to cache source and source for faster rebuilds
FROM deps-dev AS source
COPY . /app/

# ---- Builder ----
    # Only should re run if source changes
FROM source AS builder
RUN npm run build

# ---- Runtime (production) ----
FROM deps AS runtime
WORKDIR /app
ENV PROD=false
ENV NODE_ENV="dev"
ENV RELEASE=false
ENV TEST=false
EXPOSE 3000
COPY --from=builder /app/build /app/build
CMD ["npm", "run", "start"]



# ---- Runtime (dev) ----
FROM deps-dev AS runtime-dev
WORKDIR /app
ENV PROD=false
ENV NODE_ENV="dev"
ENV RELEASE=false
ENV TEST=false
EXPOSE 3000
CMD ["npx", "react-router", "dev" ,"--port", "3000", "--host", "0.0.0.0"]
