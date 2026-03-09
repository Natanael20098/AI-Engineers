package com.zcloud.platform.util;

import io.jsonwebtoken.Claims;

import java.util.List;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

/**
 * SecurityUtils – security-related utility functions for the ZCloud Security Platform.
 *
 * <p>Task 5 acceptance criteria:
 * <ul>
 *   <li>AC1: Role-based access checks return {@code true} for authorized roles.</li>
 *   <li>AC2: Test coverage includes 100% of new methods.</li>
 *   <li>AC3: No deprecated methods remain in usage.</li>
 * </ul>
 *
 * <p>Designed for thread safety on shared resources (concurrent maps, atomic operations).
 * Interoperates with {@link JwtUtil} for token-based authorization checks.
 */
public class SecurityUtils {

    private final JwtUtil jwtUtil;

    /**
     * Per-user rate-limit counters (thread-safe).
     * Used to track and throttle repeated unauthorized access attempts.
     */
    private final ConcurrentMap<String, Integer> accessAttempts = new ConcurrentHashMap<>();

    public SecurityUtils(JwtUtil jwtUtil) {
        this.jwtUtil = jwtUtil;
    }

    // -----------------------------------------------------------------------
    // Role-based access checks (Task 5 AC1)
    // -----------------------------------------------------------------------

    /**
     * Return {@code true} if the JWT token carries the required role.
     *
     * <p>Thread-safe: reads are stateless and rely on the JWT's immutable payload.
     *
     * @param token        the JWT string
     * @param requiredRole role that must be present
     * @return {@code true} if authorized; {@code false} otherwise
     */
    @SuppressWarnings("unchecked")
    public boolean hasRole(String token, String requiredRole) {
        try {
            Claims claims = jwtUtil.validateToken(token);
            List<String> roles = (List<String>) claims.get("roles");
            return roles != null && roles.contains(requiredRole);
        } catch (JwtUtil.JwtValidationException e) {
            return false;
        }
    }

    /**
     * Return {@code true} if the decoded claims contain the required role.
     *
     * <p>Useful when the token has already been validated earlier in the request
     * lifecycle and the parsed {@link Claims} object is available.
     *
     * @param claims       decoded JWT claims
     * @param requiredRole role that must be present
     * @return {@code true} if authorized
     */
    @SuppressWarnings("unchecked")
    public boolean hasRoleInClaims(Claims claims, String requiredRole) {
        if (claims == null) {
            return false;
        }
        List<String> roles = (List<String>) claims.get("roles");
        return roles != null && roles.contains(requiredRole);
    }

    /**
     * Return {@code true} if the token carries ALL of the supplied roles.
     *
     * @param token         the JWT string
     * @param requiredRoles list of roles all of which must be present
     * @return {@code true} only when every required role is found
     */
    @SuppressWarnings("unchecked")
    public boolean hasAllRoles(String token, List<String> requiredRoles) {
        if (requiredRoles == null || requiredRoles.isEmpty()) {
            return true;
        }
        try {
            Claims claims = jwtUtil.validateToken(token);
            List<String> roles = (List<String>) claims.get("roles");
            if (roles == null) {
                return false;
            }
            return roles.containsAll(requiredRoles);
        } catch (JwtUtil.JwtValidationException e) {
            return false;
        }
    }

    /**
     * Return {@code true} if the token carries ANY of the supplied roles.
     *
     * @param token         the JWT string
     * @param allowedRoles  list of roles at least one of which must be present
     * @return {@code true} when at least one allowed role is found
     */
    @SuppressWarnings("unchecked")
    public boolean hasAnyRole(String token, List<String> allowedRoles) {
        if (allowedRoles == null || allowedRoles.isEmpty()) {
            return false;
        }
        try {
            Claims claims = jwtUtil.validateToken(token);
            List<String> roles = (List<String>) claims.get("roles");
            if (roles == null) {
                return false;
            }
            for (String role : allowedRoles) {
                if (roles.contains(role)) {
                    return true;
                }
            }
            return false;
        } catch (JwtUtil.JwtValidationException e) {
            return false;
        }
    }

    // -----------------------------------------------------------------------
    // Access attempt tracking (thread-safe per Task 5 constraint)
    // -----------------------------------------------------------------------

    /**
     * Record a failed access attempt for the given identifier.
     *
     * @param identifier username or IP address
     * @return updated total attempt count
     */
    public int recordFailedAttempt(String identifier) {
        return accessAttempts.merge(identifier, 1, Integer::sum);
    }

    /**
     * Return the number of recorded failed attempts for the given identifier.
     *
     * @param identifier username or IP address
     * @return attempt count (0 if none recorded)
     */
    public int getFailedAttemptCount(String identifier) {
        return accessAttempts.getOrDefault(identifier, 0);
    }

    /**
     * Reset the failed attempt counter for the given identifier.
     *
     * @param identifier username or IP address
     */
    public void resetFailedAttempts(String identifier) {
        accessAttempts.remove(identifier);
    }

    /**
     * Return {@code true} if the identifier is locked out (≥ maxAttempts failures).
     *
     * @param identifier  username or IP address
     * @param maxAttempts maximum allowed failed attempts before lockout
     * @return {@code true} when locked out
     */
    public boolean isLockedOut(String identifier, int maxAttempts) {
        return getFailedAttemptCount(identifier) >= maxAttempts;
    }
}
