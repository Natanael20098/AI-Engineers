import { Request, Response, NextFunction } from 'express';
import jwt from 'jsonwebtoken';
import { AuthModule, TokenPayload } from '../auth/AuthModule';

// Extend Express Request to carry the authenticated token payload
declare global {
  namespace Express {
    interface Request {
      user?: TokenPayload;
    }
  }
}

/**
 * SecurityRequestMiddleware intercepts all incoming requests to verify
 * authentication and authorization credentials using JWT.
 *
 * - Returns 401 for missing, malformed, or expired tokens.
 * - Returns 403 for valid tokens that lack the required authorization.
 * - Calls next() for fully authenticated and authorized requests.
 */
export class SecurityRequestMiddleware {
  private readonly authModule: AuthModule;
  private readonly requiredRoles: string[];

  constructor(authModule: AuthModule, requiredRoles: string[] = []) {
    this.authModule = authModule;
    this.requiredRoles = requiredRoles;
  }

  /**
   * Validates the JWT token from the Authorization header.
   * Attaches the decoded payload to req.user on success.
   */
  validateRequest(req: Request, res: Response, next: NextFunction): void {
    const authHeader = req.headers['authorization'];

    if (!authHeader || !authHeader.startsWith('Bearer ')) {
      res.status(401).json({ error: 'Authentication required' });
      return;
    }

    const token = authHeader.slice(7); // strip "Bearer "

    let payload: TokenPayload;
    try {
      payload = this.authModule.validateToken(token);
    } catch (err) {
      if (err instanceof jwt.TokenExpiredError) {
        res.status(401).json({ error: 'Token has expired' });
        return;
      }
      // Covers JsonWebTokenError, NotBeforeError, and any other JWT errors.
      // Intentionally generic to avoid leaking implementation details.
      res.status(401).json({ error: 'Invalid token' });
      return;
    }

    if (!this.authModule.hasRequiredRole(payload, this.requiredRoles)) {
      res.status(403).json({ error: 'Forbidden: insufficient permissions' });
      return;
    }

    req.user = payload;
    next();
  }
}
