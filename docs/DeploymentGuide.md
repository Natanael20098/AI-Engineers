# ZCloud Security Platform — Deployment Guide

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Configuration Architecture](#configuration-architecture)
4. [Environment Variables Reference](#environment-variables-reference)
5. [Environment-Specific Setup](#environment-specific-setup)
   - [Development](#development)
   - [Testing](#testing)
   - [Production](#production)
6. [Running the Application](#running-the-application)
7. [Secrets Management](#secrets-management)
8. [Troubleshooting](#troubleshooting)

---

## Overview

The ZCloud Security Platform follows [12-factor app](https://12factor.net/) principles for configuration management. All environment-specific settings are supplied through environment variables, keeping configuration cleanly separated from code. No sensitive values are ever hardcoded.

---

## Prerequisites

| Tool        | Minimum Version |
|-------------|-----------------|
| Node.js     | 18.x            |
| npm         | 9.x             |
| TypeScript  | 5.x             |
| PostgreSQL  | 14.x            |

---

## Configuration Architecture

```
project-root/
├── configurations/
│   └── baseConfig.json        ← Non-sensitive defaults for all environments
├── src/
│   ├── ConfigLoader.ts        ← Single source of truth for config loading
│   └── index.ts               ← Application entry point (calls loadConfig())
├── .env.development           ← Development overrides (committed, no secrets)
├── .env.testing               ← Testing overrides  (committed, no secrets)
└── .env.production            ← Production template (committed, no real values)
```

### Resolution Order

When `loadConfig()` is called, values are resolved in the following precedence (higher wins):

```
process.env  >  .env.<NODE_ENV>  >  configurations/baseConfig.json
```

1. **`configurations/baseConfig.json`** — Provides structural defaults (timeouts, pool sizes, etc.) that are safe to commit and environment-agnostic.
2. **`.env.<NODE_ENV>`** — Environment-specific overrides loaded via `dotenv`. Must not contain real secrets in version control.
3. **`process.env`** — Runtime environment variables set by the OS, container runtime, or CI/CD platform. These always take highest precedence and are where secrets must live.

---

## Environment Variables Reference

| Variable                    | Required | Default (baseConfig) | Description                                              |
|-----------------------------|----------|----------------------|----------------------------------------------------------|
| `NODE_ENV`                  | Yes      | `development`        | Must be `development`, `testing`, or `production`        |
| `PORT`                      | No       | `3000`               | HTTP server port                                         |
| `HOST`                      | No       | `0.0.0.0`            | HTTP server bind address                                 |
| `LOG_LEVEL`                 | No       | `info`               | Logging verbosity (`debug`, `info`, `warn`, `error`)     |
| `DATABASE_URL`              | **Yes**  | —                    | Full PostgreSQL connection string (secret)               |
| `JWT_SECRET`                | **Yes**  | —                    | Secret key for signing JWTs — minimum 64 characters (secret) |
| `JWT_EXPIRES_IN`            | No       | `1h`                 | JWT token lifetime (e.g., `1h`, `8h`, `7d`)              |
| `CORS_ALLOWED_ORIGINS`      | No       | `[]`                 | Comma-separated list of permitted CORS origins           |
| `BCRYPT_SALT_ROUNDS`        | No       | `12`                 | bcrypt cost factor (higher = slower + more secure)       |
| `RATE_LIMIT_WINDOW_MS`      | No       | `60000`              | Rate limit window in milliseconds                        |
| `RATE_LIMIT_MAX_REQUESTS`   | No       | `100`                | Maximum requests per window per client                   |
| `CACHE_TTL_SECONDS`         | No       | `300`                | Default cache entry TTL in seconds                       |
| `REDIS_URL`                 | No       | —                    | Redis connection URL (optional caching backend)          |
| `DB_POOL_MIN`               | No       | `2`                  | Minimum database connection pool size                    |
| `DB_POOL_MAX`               | No       | `10`                 | Maximum database connection pool size                    |
| `DB_ACQUIRE_TIMEOUT_MS`     | No       | `30000`              | Timeout acquiring a DB connection (ms)                   |
| `DB_IDLE_TIMEOUT_MS`        | No       | `10000`              | Time before idle DB connections are released (ms)        |
| `APP_NAME`                  | No       | `ZCloud Security Platform` | Application name shown in logs                  |
| `APP_VERSION`               | No       | `1.0.0`              | Application version shown in logs                        |

> **Note:** Variables marked **Yes** under *Required* will cause the application to **refuse to start** if they are absent.

---

## Environment-Specific Setup

### Development

1. **Install dependencies:**
   ```bash
   npm install
   ```

2. **Review `.env.development`** in the project root. The file ships with safe placeholder values.

3. **Override secrets locally** (recommended: never modify the committed file):
   ```bash
   # Option A — export directly in your shell session
   export DATABASE_URL="postgresql://user:pass@localhost:5432/zcloud_dev"
   export JWT_SECRET="$(node -e "require('crypto').randomBytes(64).toString('hex')")"

   # Option B — create a gitignored .env.local file and source it
   cp .env.development .env.local
   # edit .env.local with real values, then:
   source .env.local
   ```

4. **Start the development server:**
   ```bash
   npm run start:dev
   ```

   Expected startup output:
   ```
   [ConfigLoader] Loaded environment file: .env.development
   [ConfigLoader] Configuration loaded successfully:
     NODE_ENV         : development
     App name         : ZCloud Security Platform
     ...
   [App] ZCloud Security Platform starting in 'development' environment on port 3000 ...
   ```

---

### Testing

1. **Ensure a dedicated test database is available** (separate from development).

2. **In CI/CD**, inject secrets as pipeline environment variables:
   ```yaml
   # Example GitHub Actions step
   env:
     NODE_ENV: testing
     DATABASE_URL: ${{ secrets.TEST_DATABASE_URL }}
     JWT_SECRET: ${{ secrets.TEST_JWT_SECRET }}
   ```

3. **Run tests:**
   ```bash
   npm run start:test
   # or your test runner, e.g.:
   # NODE_ENV=testing npx jest
   ```

---

### Production

> **Security Notice:** The `.env.production` file committed to the repository contains **only placeholder values**. Real secrets MUST be injected at runtime through your deployment platform — never committed to source control.

#### Deployment Checklist

- [ ] `DATABASE_URL` is set via secrets manager / environment injection
- [ ] `JWT_SECRET` is set to a cryptographically random string of ≥ 64 characters
- [ ] `CORS_ALLOWED_ORIGINS` lists only the production frontend domain(s)
- [ ] `REDIS_URL` is set if caching is enabled
- [ ] `NODE_ENV=production` is set in the runtime environment
- [ ] `.env.production` in the repo does **not** contain any real secrets

#### Container / Kubernetes Example

```yaml
# kubernetes/deployment.yaml (excerpt)
env:
  - name: NODE_ENV
    value: "production"
  - name: DATABASE_URL
    valueFrom:
      secretKeyRef:
        name: zcloud-secrets
        key: database-url
  - name: JWT_SECRET
    valueFrom:
      secretKeyRef:
        name: zcloud-secrets
        key: jwt-secret
```

#### Build & Start

```bash
npm run build          # Compile TypeScript → dist/
npm run start:prod     # Start compiled production server
```

---

## Running the Application

| Command               | NODE_ENV    | Description                                 |
|-----------------------|-------------|---------------------------------------------|
| `npm run start:dev`   | development | Development server via ts-node (hot reload) |
| `npm run start:test`  | testing     | Test server via ts-node                     |
| `npm run start:prod`  | production  | Compiled production server                  |
| `npm run build`       | —           | Compile TypeScript to `dist/`               |
| `npm run type-check`  | —           | Type-check without emitting files           |

---

## Secrets Management

### What counts as a secret?

- `DATABASE_URL` — contains credentials
- `JWT_SECRET` — signing key; exposure allows token forgery
- `REDIS_URL` — may contain credentials
- Any API key for third-party services

### Rules

1. **Never commit real secrets.** Treat every `.env.*` file committed to the repo as public.
2. **Use a secrets manager** in production (AWS Secrets Manager, HashiCorp Vault, GCP Secret Manager, Azure Key Vault, or Kubernetes Secrets).
3. **Rotate secrets** regularly. The `JWT_SECRET` rotation requires a rolling restart.
4. **Audit access** to your secrets manager using your cloud provider's IAM audit logs.

### Generating a secure JWT secret

```bash
node -e "require('crypto').randomBytes(64).toString('hex')"
```

---

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|--------------|-----|
| `Required environment variable 'JWT_SECRET' is not set` | Secret not injected | Set `JWT_SECRET` in env or `.env.<NODE_ENV>` |
| `Required environment variable 'DATABASE_URL' is not set` | DB URL missing | Set `DATABASE_URL` |
| `Invalid NODE_ENV '...'` | Typo or unsupported value | Use `development`, `testing`, or `production` |
| `baseConfig.json not found` | Missing config file | Ensure `configurations/baseConfig.json` exists |
| `.env.<NODE_ENV>` not loaded | Wrong working directory | Run the app from the project root |
| Config changes not reflected | Cached config | Call `loadConfig(true)` to force reload |
