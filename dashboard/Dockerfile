# Build context: the dashboard/ folder.
#   docker build -t editwar-dashboard:local dashboard

# ---- Stage 1: build the static files ----
FROM node:22-alpine AS build
WORKDIR /app
# Copy only the manifests first, so Docker caches the npm ci layer.
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npm run build

# ---- Stage 2: serve them with nginx as a non-root user ----
FROM nginxinc/nginx-unprivileged:1.27-alpine
# Where nginx forwards /api/, /ws/ and /healthz. Override it with -e API_UPSTREAM=...
ENV API_UPSTREAM=http://api:8000
COPY nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8080
