import { Request, Response, NextFunction } from 'express';

/**
 * LoggingMiddleware intercepts all incoming requests and logs metadata
 * such as HTTP method, URL, status code, and response time.
 */
export class LoggingMiddleware {
  handle(req: Request, res: Response, next: NextFunction): void {
    const start = Date.now();
    const { method, url } = req;

    res.on('finish', () => {
      const duration = Date.now() - start;
      const { statusCode } = res;
      // Avoid logging sensitive headers or bodies
      console.log(`[${new Date().toISOString()}] ${method} ${url} ${statusCode} ${duration}ms`);
    });

    next();
  }
}
