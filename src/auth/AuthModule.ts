import jwt from 'jsonwebtoken';

export interface TokenPayload {
  userId: string;
  roles: string[];
  iat: number;
  exp: number;
}

export class AuthModule {
  private readonly jwtSecret: string;

  constructor(jwtSecret?: string) {
    this.jwtSecret = jwtSecret || process.env.JWT_SECRET || '';
    if (!this.jwtSecret) {
      throw new Error('JWT_SECRET is required for AuthModule');
    }
  }

  /**
   * Validates a JWT token and returns its decoded payload.
   * Returns null if the token is invalid.
   * Throws a TokenExpiredError if the token has expired.
   */
  validateToken(token: string): TokenPayload {
    const decoded = jwt.verify(token, this.jwtSecret) as TokenPayload;
    return decoded;
  }

  /**
   * Checks whether the given payload has at least one of the required roles.
   */
  hasRequiredRole(payload: TokenPayload, requiredRoles: string[]): boolean {
    if (!requiredRoles || requiredRoles.length === 0) {
      return true;
    }
    return requiredRoles.some((role) => payload.roles.includes(role));
  }

  /**
   * Generates a signed JWT token for testing or internal use.
   */
  generateToken(payload: Omit<TokenPayload, 'iat' | 'exp'>, expiresIn = '1h'): string {
    return jwt.sign(payload, this.jwtSecret, { expiresIn } as jwt.SignOptions);
  }
}
