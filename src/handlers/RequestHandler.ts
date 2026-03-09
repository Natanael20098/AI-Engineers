import { Router, Request, Response, NextFunction } from 'express';
import { SecurityRequestMiddleware } from '../security/SecurityModule';

/**
 * RequestHandler wires up route definitions and applies the
 * SecurityRequestMiddleware to every route it registers.
 *
 * All routes defined via this handler will automatically pass through
 * validateRequest() before reaching their final handler.
 */
export class RequestHandler {
  private readonly router: Router;
  private readonly securityMiddleware: SecurityRequestMiddleware;

  constructor(securityMiddleware: SecurityRequestMiddleware) {
    this.router = Router();
    this.securityMiddleware = securityMiddleware;
    this.registerRoutes();
  }

  private securityGuard(): (req: Request, res: Response, next: NextFunction) => void {
    return (req: Request, res: Response, next: NextFunction) => {
      this.securityMiddleware.validateRequest(req, res, next);
    };
  }

  private registerRoutes(): void {
    // Health check endpoint — intentionally public (no security guard)
    this.router.get('/health', (_req: Request, res: Response) => {
      res.status(200).json({ status: 'ok' });
    });

    // All routes below are protected by SecurityRequestMiddleware
    this.router.get('/api/secure', this.securityGuard(), (_req: Request, res: Response) => {
      res.status(200).json({ message: 'Access granted', user: _req.user });
    });

    this.router.get('/api/status', this.securityGuard(), (_req: Request, res: Response) => {
      res.status(200).json({ status: 'running', user: _req.user });
    });
  }

  getRouter(): Router {
    return this.router;
  }
}
