'use strict';
/**
 * app.js – Express HTTP wrapper for UserService.
 *
 * Exposes UserService as a RESTful API for integration testing with supertest.
 *
 * Endpoints
 * ---------
 * GET  /health                  liveness probe
 * POST /auth/register           create a user account
 * POST /auth/login              authenticate and receive a JWT
 * POST /auth/logout             revoke the current JWT
 * GET  /auth/users/:userId      retrieve user profile (requires JWT)
 * POST /auth/deactivate/:userId deactivate a user account (requires JWT)
 */

const express = require('express');
const { UserService } = require('./UserService');

function createAuthApp(userService) {
  const svc = userService || new UserService();
  const app = express();
  app.use(express.json());

  // -------------------------------------------------------------------------
  // Middleware: JWT guard
  // -------------------------------------------------------------------------

  function requireAuth(req, res, next) {
    const authHeader = req.headers.authorization || '';
    if (!authHeader.startsWith('Bearer ')) {
      return res.status(401).json({ error: 'Authorization token is missing' });
    }
    const token = authHeader.slice('Bearer '.length);
    try {
      req.currentUser = svc.validateToken(token);
      return next();
    } catch (err) {
      if (err.message === 'TOKEN_EXPIRED') {
        return res.status(401).json({ error: 'Token has expired' });
      }
      if (err.message === 'TOKEN_REVOKED') {
        return res.status(401).json({ error: 'Token has been revoked' });
      }
      return res.status(401).json({ error: 'Invalid token' });
    }
  }

  // -------------------------------------------------------------------------
  // Routes
  // -------------------------------------------------------------------------

  app.get('/health', (_req, res) => {
    res.json({ status: 'ok', service: 'authentication' });
  });

  app.post('/auth/register', (req, res) => {
    const { userId, username, email, password } = req.body || {};
    if (!userId || !username || !email || !password) {
      return res.status(400).json({ error: 'userId, username, email and password are required' });
    }
    try {
      const user = svc.createUser({ userId, username, email, password });
      return res.status(201).json({ user });
    } catch (err) {
      return res.status(400).json({ error: err.message });
    }
  });

  app.post('/auth/login', (req, res) => {
    const { username, password } = req.body || {};
    if (!username || !password) {
      return res.status(400).json({ error: 'username and password are required' });
    }
    try {
      const result = svc.authenticateUser(username, password);
      return res.status(200).json(result);
    } catch (err) {
      if (err.message === 'ACCOUNT_DISABLED') {
        return res.status(401).json({ error: 'Account is disabled' });
      }
      // INVALID_CREDENTIALS or anything else – same 401 to prevent enumeration
      return res.status(401).json({ error: 'Invalid username or password' });
    }
  });

  app.post('/auth/logout', requireAuth, (req, res) => {
    const authHeader = req.headers.authorization || '';
    const token = authHeader.slice('Bearer '.length);
    try {
      svc.revokeToken(token);
      return res.status(200).json({ message: 'Successfully logged out' });
    } catch (err) {
      return res.status(401).json({ error: err.message });
    }
  });

  app.get('/auth/users/:userId', requireAuth, (req, res) => {
    const user = svc.getUserById(req.params.userId);
    if (!user) {
      return res.status(404).json({ error: `User '${req.params.userId}' not found` });
    }
    return res.status(200).json({ user });
  });

  app.post('/auth/deactivate/:userId', requireAuth, (req, res) => {
    try {
      const user = svc.deactivateUser(req.params.userId);
      return res.status(200).json({ user });
    } catch (err) {
      return res.status(404).json({ error: err.message });
    }
  });

  return app;
}

module.exports = { createAuthApp };

if (require.main === module) {
  const app = createAuthApp();
  const PORT = process.env.PORT || 3001;
  app.listen(PORT, () => {
    console.log(`Auth service listening on port ${PORT}`);
  });
}
