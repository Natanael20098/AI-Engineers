# ZCloud Security Platform

A comprehensive solution designed to manage security-related functionalities within organizational infrastructure. Built as a monolithic API that integrates various security operations — handling web requests, managing data, and ensuring secure operations at scale.

---

## Tech Stack

- **Runtime:** Node.js 18+
- **Language:** TypeScript 5
- **Additional:** Python 3 (supporting tooling)
- **Database:** PostgreSQL 14+
- **Cache:** Redis (optional)

---

## Project Structure

```
.
├── configurations/
│   └── baseConfig.json        # Non-sensitive base defaults for all environments
├── src/
│   ├── ConfigLoader.ts        # Central configuration loader (12-factor)
│   └── index.ts               # Application entry point
├── docs/
│   └── DeploymentGuide.md     # Full deployment & configuration documentation
├── .env.development           # Development environment template
├── .env.testing               # Testing environment template
├── .env.production            # Production environment template (no real secrets)
├── package.json
└── tsconfig.json
```

---

## Quick Start

### 1. Install dependencies

```bash
npm install
```

### 2. Configure environment

The project ships with `.env.development`, `.env.testing`, and `.env.production` template files. Two variables **must** be set before the app starts:

```bash
export DATABASE_URL="postgresql://user:pass@localhost:5432/zcloud_dev"
export JWT_SECRET="$(node -e "require('crypto').randomBytes(64).toString('hex')")"
```

### 3. Run

```bash
# Development (ts-node)
npm run start:dev

# Testing
npm run start:test

# Production (compiled)
npm run build && npm run start:prod
```

---

## Configuration

The application uses a layered configuration system following [12-factor](https://12factor.net/) principles:

| Layer | Source | Priority |
|-------|--------|----------|
| 1 (lowest) | `configurations/baseConfig.json` | Non-sensitive defaults |
| 2 | `.env.<NODE_ENV>` | Environment-specific overrides |
| 3 (highest) | `process.env` | Runtime / CI injection (secrets live here) |

`ConfigLoader.ts` is the single entry point for all configuration. Call `loadConfig()` once at startup; use `getConfig()` everywhere else.

See **[docs/DeploymentGuide.md](docs/DeploymentGuide.md)** for the full reference, including all environment variables, secrets management guidance, and deployment checklists.

---

## Security Notes

- Sensitive values (`JWT_SECRET`, `DATABASE_URL`, etc.) are **never** hardcoded.
- `.env.*` files committed to the repository contain only safe placeholder values.
- Real secrets must be injected at runtime via your secrets manager or CI/CD platform.
- The application will **refuse to start** if required secrets are missing.
