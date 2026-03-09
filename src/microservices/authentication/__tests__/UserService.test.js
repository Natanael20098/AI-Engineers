'use strict';
/**
 * Unit tests for UserService.js
 *
 * Acceptance criteria:
 *  - All unit tests pass success criteria on local and CI/CD environment.
 *  - Critical functions in UserService.js achieve over 90% test coverage.
 *  - Each critical function has at least one success and one failure case.
 *
 * Critical functions under test:
 *  - createUser()
 *  - authenticateUser()
 *  - getUserById()
 *  - validateToken()
 *  - revokeToken()
 *  - deactivateUser()
 */

const { UserService } = require('../UserService');

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

let svc;

beforeEach(() => {
  svc = new UserService();
  svc._reset();
});

afterEach(() => {
  svc._reset();
});

// ---------------------------------------------------------------------------
// createUser()
// ---------------------------------------------------------------------------

describe('createUser()', () => {
  test('SUCCESS – creates a user and returns sanitized record', () => {
    const user = svc.createUser({
      userId: 'user-001',
      username: 'alice',
      email: 'alice@example.com',
      password: 'secure_password',
    });

    expect(user.userId).toBe('user-001');
    expect(user.username).toBe('alice');
    expect(user.email).toBe('alice@example.com');
    expect(user.isActive).toBe(true);
    expect(user.createdAt).toBeDefined();
  });

  test('SUCCESS – password is not exposed in returned record', () => {
    const user = svc.createUser({
      userId: 'user-002',
      username: 'bob',
      email: 'bob@example.com',
      password: 'password123',
    });

    expect(user.passwordHash).toBeUndefined();
    expect(user.passwordSalt).toBeUndefined();
  });

  test('SUCCESS – creates an inactive user when isActive=false', () => {
    const user = svc.createUser({
      userId: 'user-003',
      username: 'carol',
      email: 'carol@example.com',
      password: 'pass',
      isActive: false,
    });

    expect(user.isActive).toBe(false);
  });

  test('FAILURE – throws if userId is missing', () => {
    expect(() =>
      svc.createUser({ username: 'alice', email: 'a@b.com', password: 'pw' })
    ).toThrow('userId is required');
  });

  test('FAILURE – throws if username is missing', () => {
    expect(() =>
      svc.createUser({ userId: 'u1', email: 'a@b.com', password: 'pw' })
    ).toThrow('username is required');
  });

  test('FAILURE – throws if email is missing', () => {
    expect(() =>
      svc.createUser({ userId: 'u1', username: 'alice', password: 'pw' })
    ).toThrow('email is required');
  });

  test('FAILURE – throws if password is missing', () => {
    expect(() =>
      svc.createUser({ userId: 'u1', username: 'alice', email: 'a@b.com' })
    ).toThrow('password is required');
  });

  test('FAILURE – throws if username already exists', () => {
    svc.createUser({
      userId: 'u1',
      username: 'alice',
      email: 'a@b.com',
      password: 'pw',
    });

    expect(() =>
      svc.createUser({
        userId: 'u2',
        username: 'alice',
        email: 'a2@b.com',
        password: 'pw2',
      })
    ).toThrow("User 'alice' already exists");
  });

  test('FAILURE – throws if called with no arguments', () => {
    expect(() => svc.createUser()).toThrow();
  });
});

// ---------------------------------------------------------------------------
// authenticateUser()
// ---------------------------------------------------------------------------

describe('authenticateUser()', () => {
  beforeEach(() => {
    svc.createUser({
      userId: 'user-001',
      username: 'alice',
      email: 'alice@example.com',
      password: 'correct_password',
    });
  });

  test('SUCCESS – returns token and user for valid credentials', () => {
    const result = svc.authenticateUser('alice', 'correct_password');

    expect(result.token).toBeDefined();
    expect(typeof result.token).toBe('string');
    expect(result.user).toBeDefined();
    expect(result.user.username).toBe('alice');
    expect(result.user.email).toBe('alice@example.com');
  });

  test('SUCCESS – returned token is a valid JWT with required claims', () => {
    const { token } = svc.authenticateUser('alice', 'correct_password');
    const parts = token.split('.');

    expect(parts).toHaveLength(3);

    const payload = JSON.parse(Buffer.from(parts[1], 'base64url').toString('utf8'));
    expect(payload.sub).toBe('user-001');
    expect(payload.username).toBe('alice');
    expect(payload.email).toBe('alice@example.com');
    expect(payload.jti).toBeDefined();
    expect(payload.iat).toBeDefined();
    expect(payload.exp).toBeGreaterThan(payload.iat);
  });

  test('SUCCESS – password not present in returned user object', () => {
    const { user } = svc.authenticateUser('alice', 'correct_password');

    expect(user.passwordHash).toBeUndefined();
    expect(user.passwordSalt).toBeUndefined();
  });

  test('FAILURE – throws INVALID_CREDENTIALS for wrong password', () => {
    expect(() => svc.authenticateUser('alice', 'wrong_password')).toThrow(
      'INVALID_CREDENTIALS'
    );
  });

  test('FAILURE – throws INVALID_CREDENTIALS for unknown username', () => {
    expect(() => svc.authenticateUser('ghost', 'any_pass')).toThrow(
      'INVALID_CREDENTIALS'
    );
  });

  test('FAILURE – throws ACCOUNT_DISABLED for inactive user', () => {
    svc.createUser({
      userId: 'user-002',
      username: 'inactive_bob',
      email: 'bob@example.com',
      password: 'pw',
      isActive: false,
    });

    expect(() => svc.authenticateUser('inactive_bob', 'pw')).toThrow(
      'ACCOUNT_DISABLED'
    );
  });

  test('FAILURE – throws if username is missing', () => {
    expect(() => svc.authenticateUser('', 'pw')).toThrow(
      'username and password are required'
    );
  });

  test('FAILURE – throws if password is missing', () => {
    expect(() => svc.authenticateUser('alice', '')).toThrow(
      'username and password are required'
    );
  });
});

// ---------------------------------------------------------------------------
// getUserById()
// ---------------------------------------------------------------------------

describe('getUserById()', () => {
  test('SUCCESS – returns sanitized user for known userId', () => {
    svc.createUser({
      userId: 'user-001',
      username: 'alice',
      email: 'alice@example.com',
      password: 'pw',
    });

    const user = svc.getUserById('user-001');

    expect(user).not.toBeNull();
    expect(user.userId).toBe('user-001');
    expect(user.username).toBe('alice');
    expect(user.passwordHash).toBeUndefined();
  });

  test('FAILURE – returns null for unknown userId', () => {
    const result = svc.getUserById('does-not-exist');
    expect(result).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// validateToken()
// ---------------------------------------------------------------------------

describe('validateToken()', () => {
  let token;

  beforeEach(() => {
    svc.createUser({
      userId: 'user-001',
      username: 'alice',
      email: 'alice@example.com',
      password: 'pw',
    });
    ({ token } = svc.authenticateUser('alice', 'pw'));
  });

  test('SUCCESS – returns decoded payload for a valid token', () => {
    const payload = svc.validateToken(token);

    expect(payload.username).toBe('alice');
    expect(payload.sub).toBe('user-001');
    expect(payload.jti).toBeDefined();
  });

  test('FAILURE – throws TOKEN_EXPIRED for an expired token', () => {
    const jwt = require('jsonwebtoken');
    const expiredToken = jwt.sign(
      { sub: 'user-001', username: 'alice', jti: 'jti-1', iat: 1, exp: 1 },
      process.env.JWT_SECRET_KEY || 'dev-secret-key-change-in-prod'
    );

    expect(() => svc.validateToken(expiredToken)).toThrow('TOKEN_EXPIRED');
  });

  test('FAILURE – throws INVALID_TOKEN for a tampered token', () => {
    expect(() => svc.validateToken(token + 'tampered')).toThrow('INVALID_TOKEN');
  });

  test('FAILURE – throws INVALID_TOKEN for an empty string', () => {
    expect(() => svc.validateToken('')).toThrow();
  });

  test('FAILURE – throws TOKEN_REVOKED after revokeToken() is called', () => {
    svc.revokeToken(token);
    expect(() => svc.validateToken(token)).toThrow('TOKEN_REVOKED');
  });
});

// ---------------------------------------------------------------------------
// revokeToken()
// ---------------------------------------------------------------------------

describe('revokeToken()', () => {
  let token;

  beforeEach(() => {
    svc.createUser({
      userId: 'user-001',
      username: 'alice',
      email: 'alice@example.com',
      password: 'pw',
    });
    ({ token } = svc.authenticateUser('alice', 'pw'));
  });

  test('SUCCESS – revokes a valid token', () => {
    const result = svc.revokeToken(token);
    expect(result.message).toContain('revoked');
  });

  test('FAILURE – attempting to revoke an already-revoked token throws TOKEN_REVOKED', () => {
    svc.revokeToken(token);
    expect(() => svc.revokeToken(token)).toThrow('TOKEN_REVOKED');
  });

  test('FAILURE – attempting to revoke a tampered token throws', () => {
    expect(() => svc.revokeToken(token + 'xxx')).toThrow();
  });
});

// ---------------------------------------------------------------------------
// deactivateUser()
// ---------------------------------------------------------------------------

describe('deactivateUser()', () => {
  beforeEach(() => {
    svc.createUser({
      userId: 'user-001',
      username: 'alice',
      email: 'alice@example.com',
      password: 'pw',
    });
  });

  test('SUCCESS – marks the user as inactive', () => {
    const user = svc.deactivateUser('user-001');
    expect(user.isActive).toBe(false);
  });

  test('SUCCESS – deactivated user cannot log in', () => {
    svc.deactivateUser('user-001');
    expect(() => svc.authenticateUser('alice', 'pw')).toThrow('ACCOUNT_DISABLED');
  });

  test('FAILURE – throws if userId does not exist', () => {
    expect(() => svc.deactivateUser('ghost-id')).toThrow("User 'ghost-id' not found");
  });
});

// ---------------------------------------------------------------------------
// Token uniqueness (edge cases)
// ---------------------------------------------------------------------------

describe('Token uniqueness', () => {
  test('Two logins for the same user produce different tokens', () => {
    svc.createUser({
      userId: 'user-001',
      username: 'alice',
      email: 'a@b.com',
      password: 'pw',
    });
    const { token: t1 } = svc.authenticateUser('alice', 'pw');
    const { token: t2 } = svc.authenticateUser('alice', 'pw');

    expect(t1).not.toBe(t2);
  });
});
