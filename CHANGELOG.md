# Changelog

## [Unreleased] - 2026-03-09

### Added
- **`SecurityRequestMiddleware`** (`src/security/SecurityModule.ts`): New middleware class that intercepts all incoming requests to perform JWT authentication and role-based authorization.
  - Returns `401` for missing, malformed, or expired JWTs.
  - Returns `403` for valid tokens that lack the required roles.
  - Attaches decoded `TokenPayload` to `req.user` for downstream handlers.
  - Sensitive error details are never exposed to the client.
- **`AuthModule`** (`src/auth/AuthModule.ts`): JWT utility class exposing `validateToken()`, `hasRequiredRole()`, and `generateToken()` methods.
- **`LoggingMiddleware`** (`src/middleware/LoggingMiddleware.ts`): Reference middleware that logs HTTP method, URL, status code, and response time for every request.
- **`RequestHandler`** (`src/handlers/RequestHandler.ts`): Express router that applies `SecurityRequestMiddleware` as a guard on all protected routes.
- **`serverConfig.ts`** (`src/config/serverConfig.ts`): Express app factory that wires the middleware chain (`LoggingMiddleware` → `SecurityRequestMiddleware` → `RequestHandler`).
- **Integration tests** (`src/tests/SecurityModule.test.ts`): Full test suite covering authentication, authorization, and middleware invocation using Jest + Supertest.
- **Project scaffolding**: `package.json`, `tsconfig.json`, `jest.config.js`, `.gitignore`, `README.md`.
