'use strict';
/**
 * UserService.js – Authentication microservice business logic.
 *
 * Handles user creation, credential validation, JWT issuance, and token
 * verification for the Natanael Security Platform.
 *
 * This module is intentionally dependency-free (no Express) so that it can
 * be unit-tested in isolation and imported by the HTTP layer (app.js) or by
 * integration tests via supertest.
 */

const crypto = require('crypto');
const jwt = require('jsonwebtoken');

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

const JWT_SECRET = process.env.JWT_SECRET_KEY || 'dev-secret-key-change-in-prod';
const JWT_EXPIRY = process.env.JWT_EXPIRY_MINUTES
  ? parseInt(process.env.JWT_EXPIRY_MINUTES, 10) * 60
  : 3600; // seconds

// ---------------------------------------------------------------------------
// In-memory store (replaced by a real DB in production)
// ---------------------------------------------------------------------------

/** @type {Map<string, Object>} username → user record */
const _userStore = new Map();

/** @type {Set<string>} revoked JTI values */
const _blacklist = new Set();

// ---------------------------------------------------------------------------
// Password utilities
// ---------------------------------------------------------------------------

/**
 * Hash a plaintext password with PBKDF2.
 *
 * @param {string} password
 * @param {string} [salt]  – hex string; generated when omitted
 * @returns {{ hash: string, salt: string }}
 */
function _hashPassword(password, salt) {
  if (typeof password !== 'string' || password.length === 0) {
    throw new Error('password must be a non-empty string');
  }
  const useSalt = salt || crypto.randomBytes(16).toString('hex');
  const hash = crypto
    .pbkdf2Sync(password, useSalt, 100_000, 32, 'sha256')
    .toString('hex');
  return { hash, salt: useSalt };
}

// ---------------------------------------------------------------------------
// UserService
// ---------------------------------------------------------------------------

class UserService {
  /**
   * Create a new user account.
   *
   * @param {{ userId: string, username: string, email: string, password: string, isActive?: boolean }} userData
   * @returns {Object} The persisted user record (without password fields).
   * @throws {Error} If required fields are missing or username already exists.
   */
  createUser({ userId, username, email, password, isActive = true } = {}) {
    if (!userId || typeof userId !== 'string') {
      throw new Error('userId is required');
    }
    if (!username || typeof username !== 'string') {
      throw new Error('username is required');
    }
    if (!email || typeof email !== 'string') {
      throw new Error('email is required');
    }
    if (!password || typeof password !== 'string') {
      throw new Error('password is required');
    }
    if (_userStore.has(username)) {
      throw new Error(`User '${username}' already exists`);
    }

    const { hash, salt } = _hashPassword(password);
    const user = {
      userId,
      username,
      email,
      passwordHash: hash,
      passwordSalt: salt,
      isActive,
      createdAt: new Date().toISOString(),
    };
    _userStore.set(username, user);
    return this._sanitize(user);
  }

  /**
   * Authenticate a user with username + password.
   *
   * @param {string} username
   * @param {string} password
   * @returns {{ token: string, user: Object }} JWT and sanitized user profile.
   * @throws {Error} 'INVALID_CREDENTIALS' if authentication fails.
   * @throws {Error} 'ACCOUNT_DISABLED' if the account is inactive.
   */
  authenticateUser(username, password) {
    if (!username || !password) {
      throw new Error('username and password are required');
    }

    const user = _userStore.get(username);

    if (!user) {
      // Prevent username enumeration – same message for unknown user / wrong pw
      throw new Error('INVALID_CREDENTIALS');
    }

    const { hash } = _hashPassword(password, user.passwordSalt);
    if (hash !== user.passwordHash) {
      throw new Error('INVALID_CREDENTIALS');
    }

    if (!user.isActive) {
      throw new Error('ACCOUNT_DISABLED');
    }

    const jti = crypto.randomUUID();
    const now = Math.floor(Date.now() / 1000);
    const payload = {
      sub: user.userId,
      username: user.username,
      email: user.email,
      jti,
      iat: now,
      exp: now + JWT_EXPIRY,
    };
    const token = jwt.sign(payload, JWT_SECRET, { algorithm: 'HS256' });
    return { token, user: this._sanitize(user) };
  }

  /**
   * Look up a user by their unique identifier.
   *
   * @param {string} userId
   * @returns {Object|null} Sanitized user record or null.
   */
  getUserById(userId) {
    for (const user of _userStore.values()) {
      if (user.userId === userId) {
        return this._sanitize(user);
      }
    }
    return null;
  }

  /**
   * Validate a JWT and confirm it has not been revoked.
   *
   * @param {string} token
   * @returns {Object} Decoded payload.
   * @throws {Error} If token is invalid, expired, or revoked.
   */
  validateToken(token) {
    if (!token) {
      throw new Error('token is required');
    }
    let payload;
    try {
      payload = jwt.verify(token, JWT_SECRET, { algorithms: ['HS256'] });
    } catch (err) {
      if (err.name === 'TokenExpiredError') {
        throw new Error('TOKEN_EXPIRED');
      }
      throw new Error('INVALID_TOKEN');
    }
    if (_blacklist.has(payload.jti)) {
      throw new Error('TOKEN_REVOKED');
    }
    return payload;
  }

  /**
   * Revoke a JWT by adding its JTI to the blacklist.
   *
   * @param {string} token
   * @returns {{ message: string }}
   * @throws {Error} If the token is invalid or already revoked.
   */
  revokeToken(token) {
    const payload = this.validateToken(token);
    _blacklist.add(payload.jti);
    return { message: 'Token revoked successfully' };
  }

  /**
   * Deactivate a user account.
   *
   * @param {string} userId
   * @returns {Object} Updated (sanitized) user record.
   * @throws {Error} If the user is not found.
   */
  deactivateUser(userId) {
    for (const [key, user] of _userStore.entries()) {
      if (user.userId === userId) {
        user.isActive = false;
        _userStore.set(key, user);
        return this._sanitize(user);
      }
    }
    throw new Error(`User '${userId}' not found`);
  }

  // ---------------------------------------------------------------------------
  // Internal helpers
  // ---------------------------------------------------------------------------

  /** Strip credential fields before returning a user object. */
  _sanitize(user) {
    const { passwordHash, passwordSalt, ...safe } = user; // eslint-disable-line no-unused-vars
    return safe;
  }

  /** Clear all internal state (used in tests). */
  _reset() {
    _userStore.clear();
    _blacklist.clear();
  }
}

module.exports = { UserService, _userStore, _blacklist };
