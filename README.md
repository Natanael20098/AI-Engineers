# ZCloud Security Platform

A Node.js/TypeScript security management platform that provides JWT-based authentication and authorization middleware for protecting web API endpoints.

## Tech Stack

- **Runtime**: Node.js
- **Language**: TypeScript (strict mode)
- **HTTP Framework**: Express
- **Authentication**: JSON Web Tokens (JWT) via `jsonwebtoken`
- **Testing**: Jest + Supertest

## Architecture

```
src/
├── auth/
│   └── AuthModule.ts          # JWT validation and role checking
├── config/
│   └── serverConfig.ts        # Express app factory & middleware chain
├── handlers/
│   └── RequestHandler.ts      # Route definitions with security guards
├── middleware/
│   └── LoggingMiddleware.ts   # Request/response logging
├── security/
│   └── SecurityModule.ts      # SecurityRequestMiddleware (auth + authz)
├── tests/
│   └── SecurityModule.test.ts # Integration tests
└── index.ts                   # Server entry point
```

### Middleware Chain

Every request passes through the following chain in order:

1. **LoggingMiddleware** — logs method, URL, status code, and response time
2. **SecurityRequestMiddleware** — validates JWT and enforces role-based access
3. **RequestHandler** — routes requests to the appropriate handler

### Response Codes

| Scenario | Status |
|---|---|
| No / malformed `Authorization` header | `401` |
| Invalid or expired JWT | `401` |
| Valid JWT, insufficient roles | `403` |
| Valid JWT, authorized | `200` |

## Setup

### Prerequisites

- Node.js >= 18
- npm

### Install

```bash
npm install
```

### Environment Variables

| Variable | Required | Description |
|---|---|---|
| `JWT_SECRET` | Yes | Secret key used to sign and verify JWTs |
| `PORT` | No | HTTP port (default: `3000`) |

### Run

```bash
# Development (ts-node)
JWT_SECRET=mysecret npm run dev

# Production
npm run build
JWT_SECRET=mysecret npm start
```

### Test

```bash
npm test
# with coverage
npm run test:coverage
```

## Endpoints

| Method | Path | Auth Required | Description |
|---|---|---|---|
| `GET` | `/health` | No | Health check |
| `GET` | `/api/secure` | Yes | Example protected endpoint |
| `GET` | `/api/status` | Yes | Server status |
