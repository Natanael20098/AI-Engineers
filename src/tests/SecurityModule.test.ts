import request from 'supertest';
import { createServer } from '../config/serverConfig';
import { AuthModule } from '../auth/AuthModule';

const TEST_JWT_SECRET = 'test-secret-key-for-unit-tests';

describe('SecurityRequestMiddleware', () => {
  const app = createServer({ port: 0, jwtSecret: TEST_JWT_SECRET, requiredRoles: [] });
  const authModule = new AuthModule(TEST_JWT_SECRET);

  describe('Authentication', () => {
    it('returns 401 when Authorization header is missing', async () => {
      const res = await request(app).get('/api/secure');
      expect(res.status).toBe(401);
      expect(res.body).toHaveProperty('error');
    });

    it('returns 401 when Authorization header has wrong scheme', async () => {
      const res = await request(app).get('/api/secure').set('Authorization', 'Basic dXNlcjpwYXNz');
      expect(res.status).toBe(401);
      expect(res.body).toHaveProperty('error');
    });

    it('returns 401 for a malformed token', async () => {
      const res = await request(app).get('/api/secure').set('Authorization', 'Bearer not.a.valid.token');
      expect(res.status).toBe(401);
      expect(res.body.error).toBe('Invalid token');
    });

    it('returns 401 for an expired token', async () => {
      // Create a token that expired 1 second ago
      const expiredToken = authModule.generateToken({ userId: 'u1', roles: [] }, '-1s');
      const res = await request(app).get('/api/secure').set('Authorization', `Bearer ${expiredToken}`);
      expect(res.status).toBe(401);
      expect(res.body.error).toBe('Token has expired');
    });

    it('does not expose internal error details for invalid tokens', async () => {
      const res = await request(app).get('/api/secure').set('Authorization', 'Bearer bad.token');
      expect(res.status).toBe(401);
      // Should not contain stack traces or implementation details
      expect(JSON.stringify(res.body)).not.toMatch(/stack|at Object|jsonwebtoken/i);
    });
  });

  describe('Authorization', () => {
    it('returns 403 when token is valid but lacks required roles', async () => {
      const appWithRoles = createServer({
        port: 0,
        jwtSecret: TEST_JWT_SECRET,
        requiredRoles: ['admin'],
      });
      const token = authModule.generateToken({ userId: 'u1', roles: ['viewer'] });
      const res = await request(appWithRoles).get('/api/secure').set('Authorization', `Bearer ${token}`);
      expect(res.status).toBe(403);
      expect(res.body.error).toBe('Forbidden: insufficient permissions');
    });

    it('allows access when token has the required role', async () => {
      const appWithRoles = createServer({
        port: 0,
        jwtSecret: TEST_JWT_SECRET,
        requiredRoles: ['admin'],
      });
      const token = authModule.generateToken({ userId: 'u1', roles: ['admin'] });
      const res = await request(appWithRoles).get('/api/secure').set('Authorization', `Bearer ${token}`);
      expect(res.status).toBe(200);
    });
  });

  describe('Valid requests', () => {
    it('returns 200 and proceeds to handler with a valid token', async () => {
      const token = authModule.generateToken({ userId: 'u1', roles: ['user'] });
      const res = await request(app).get('/api/secure').set('Authorization', `Bearer ${token}`);
      expect(res.status).toBe(200);
      expect(res.body).toHaveProperty('message', 'Access granted');
    });

    it('attaches decoded user payload to the request', async () => {
      const token = authModule.generateToken({ userId: 'user-42', roles: ['user', 'editor'] });
      const res = await request(app).get('/api/secure').set('Authorization', `Bearer ${token}`);
      expect(res.status).toBe(200);
      expect(res.body.user).toMatchObject({ userId: 'user-42', roles: expect.arrayContaining(['user', 'editor']) });
    });

    it('health endpoint is publicly accessible without a token', async () => {
      const res = await request(app).get('/health');
      expect(res.status).toBe(200);
      expect(res.body).toHaveProperty('status', 'ok');
    });
  });

  describe('Middleware invocation', () => {
    it('invokes SecurityRequestMiddleware for all protected routes', async () => {
      const routes = ['/api/secure', '/api/status'];
      for (const route of routes) {
        const res = await request(app).get(route);
        // Without a token every protected route must reject with 401
        expect(res.status).toBe(401);
      }
    });
  });
});
