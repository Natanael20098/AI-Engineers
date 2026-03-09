# Changelog

All notable changes to ZCloud Security Platform will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased] — 2026-03-09

### Added

- **`configurations/baseConfig.json`** — Non-sensitive baseline configuration covering app, server, security, database pool, rate limiting, and cache settings shared across all environments.
- **`src/ConfigLoader.ts`** — Central configuration loader implementing 12-factor app principles. Resolves configuration by merging `baseConfig.json` defaults with `.env.<NODE_ENV>` file values and runtime `process.env` variables (highest priority). Validates required secrets (`JWT_SECRET`, `DATABASE_URL`) at startup and logs non-sensitive diagnostic information to the console. Exposes `loadConfig()` and `getConfig()` functions; caches the resolved config after first load.
- **`src/index.ts`** — Application entry point that calls `loadConfig()` at startup.
- **`.env.development`** — Development environment template with safe placeholder values and inline documentation.
- **`.env.testing`** — Testing / CI environment template with relaxed rate limits and dedicated test database placeholders.
- **`.env.production`** — Production environment template with `INJECT_AT_DEPLOY_TIME` markers for all secrets, enforcing that no real credentials are committed.
- **`docs/DeploymentGuide.md`** — Comprehensive deployment and configuration guide covering: configuration architecture, full environment variable reference, per-environment setup instructions, secrets management best practices, and a troubleshooting table.
- **`package.json`** — Node.js project manifest with `dotenv` runtime dependency, TypeScript dev dependencies, and `start:dev / start:test / start:prod / build` npm scripts.
- **`tsconfig.json`** — TypeScript compiler configuration targeting ES2020 with strict mode and JSON module resolution enabled.
- **`.gitignore`** — Ignores `node_modules/`, `dist/`, `.env.*.local` (local secret overrides), Python artifacts, and common editor/OS files.
- **`Readme.md`** — Updated with project description, tech stack, directory structure, quick-start instructions, and configuration architecture summary.
