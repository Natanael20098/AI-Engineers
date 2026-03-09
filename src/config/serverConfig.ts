import express, { Application } from 'express';
import { AuthModule } from '../auth/AuthModule';
import { LoggingMiddleware } from '../middleware/LoggingMiddleware';
import { SecurityRequestMiddleware } from '../security/SecurityModule';
import { RequestHandler } from '../handlers/RequestHandler';

export interface ServerConfig {
  port: number;
  jwtSecret: string;
  requiredRoles?: string[];
}

/**
 * Builds and returns a configured Express application.
 *
 * Middleware chain (applied in order):
 *  1. LoggingMiddleware  — structured request/response logging
 *  2. SecurityRequestMiddleware — JWT authentication & role-based authorization
 *  3. RequestHandler routes — protected application endpoints
 */
export function createServer(config: ServerConfig): Application {
  const app = express();

  // Built-in body parsing
  app.use(express.json());
  app.use(express.urlencoded({ extended: false }));

  // 1. Logging middleware — logs every incoming request
  const loggingMiddleware = new LoggingMiddleware();
  app.use((req, res, next) => loggingMiddleware.handle(req, res, next));

  // 2. Security middleware — validates JWT and enforces role-based access
  const authModule = new AuthModule(config.jwtSecret);
  const securityMiddleware = new SecurityRequestMiddleware(authModule, config.requiredRoles ?? []);

  // 3. Route handler — incorporates security guard per-route
  const requestHandler = new RequestHandler(securityMiddleware);
  app.use(requestHandler.getRouter());

  // Generic 404 handler
  app.use((_req, res) => {
    res.status(404).json({ error: 'Not found' });
  });

  return app;
}
