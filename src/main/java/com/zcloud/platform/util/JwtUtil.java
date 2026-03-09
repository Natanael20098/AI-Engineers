package com.zcloud.platform.util;

import io.jsonwebtoken.*;
import io.jsonwebtoken.security.Keys;

import java.nio.charset.StandardCharsets;
import java.security.Key;
import java.util.Date;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/**
 * JwtUtil – manages JWT token generation, renewal, and validation.
 *
 * <p>Task 1 acceptance criteria:
 * <ul>
 *   <li>AC1: Valid JWT token includes {@code userId}, {@code roles}, and {@code expiry}.</li>
 *   <li>AC2: Expired tokens are successfully renewed.</li>
 *   <li>AC3: Tokens with incorrect payloads return 401 error (throws {@link JwtValidationException}).</li>
 * </ul>
 */
public class JwtUtil {

    /** Default token lifetime in milliseconds (60 minutes). */
    private static final long DEFAULT_EXPIRY_MS = 60L * 60 * 1000;

    private final Key signingKey;
    private final long expiryMs;

    public JwtUtil(String secret) {
        this(secret, DEFAULT_EXPIRY_MS);
    }

    public JwtUtil(String secret, long expiryMs) {
        this.signingKey = Keys.hmacShaKeyFor(secret.getBytes(StandardCharsets.UTF_8));
        this.expiryMs = expiryMs;
    }

    // -----------------------------------------------------------------------
    // Token generation (Task 1 AC1)
    // -----------------------------------------------------------------------

    /**
     * Generate a signed JWT for the given user.
     *
     * <p>The token payload includes:
     * <ul>
     *   <li>{@code userId} – the user's unique identifier</li>
     *   <li>{@code roles}  – the user's roles list</li>
     *   <li>{@code expiry} – ISO-8601 expiry timestamp</li>
     *   <li>{@code jti}    – unique token ID for revocation</li>
     * </ul>
     *
     * @param userId unique user identifier
     * @param roles  list of role strings
     * @return signed JWT string
     */
    public String generateToken(String userId, List<String> roles) {
        Date now = new Date();
        Date expiry = new Date(now.getTime() + expiryMs);

        return Jwts.builder()
                .claim("userId", userId)
                .claim("roles", roles)
                .claim("expiry", expiry.toInstant().toString())
                .id(UUID.randomUUID().toString())
                .issuedAt(now)
                .expiration(expiry)
                .signWith(signingKey)
                .compact();
    }

    // -----------------------------------------------------------------------
    // Token renewal (Task 1 AC2)
    // -----------------------------------------------------------------------

    /**
     * Renew an access token, even if it has expired.
     *
     * <p>Parses the token ignoring expiry, extracts the identity claims, and
     * issues a fresh token with a new expiry.
     *
     * @param token the (possibly expired) JWT string
     * @return a new signed JWT with refreshed expiry
     * @throws JwtValidationException if the token cannot be parsed at all
     */
    @SuppressWarnings("unchecked")
    public String renewToken(String token) {
        Claims claims;
        try {
            claims = Jwts.parser()
                    .verifyWith((javax.crypto.SecretKey) signingKey)
                    .clockSkewSeconds(Long.MAX_VALUE / 1000)
                    .build()
                    .parseSignedClaims(token)
                    .getPayload();
        } catch (JwtException e) {
            throw new JwtValidationException("Cannot renew invalid token: " + e.getMessage(), e);
        }

        String userId = (String) claims.get("userId");
        List<String> roles = (List<String>) claims.get("roles");
        if (userId == null) {
            throw new JwtValidationException("Token payload missing required userId claim");
        }

        return generateToken(userId, roles != null ? roles : List.of());
    }

    // -----------------------------------------------------------------------
    // Token validation (Task 1 AC3)
    // -----------------------------------------------------------------------

    /**
     * Validate a JWT token and verify the user has the required role.
     *
     * <p>Rejects tokens that:
     * <ul>
     *   <li>are expired</li>
     *   <li>have an invalid signature</li>
     *   <li>are missing required payload fields ({@code userId}, {@code roles})</li>
     *   <li>do not contain the {@code requiredRole}</li>
     * </ul>
     *
     * @param token        the JWT string to validate
     * @param requiredRole role that must be present in the token's roles claim
     * @return decoded {@link Claims} if valid
     * @throws JwtValidationException with a 401-semantic message on any failure
     */
    @SuppressWarnings("unchecked")
    public Claims validateToken(String token, String requiredRole) {
        Claims claims = parseAndValidateClaims(token);

        List<String> roles = (List<String>) claims.get("roles");
        if (roles == null || !roles.contains(requiredRole)) {
            throw new JwtValidationException(
                    "401: User does not have required role: " + requiredRole);
        }

        return claims;
    }

    /**
     * Validate a JWT token without role-checking.
     *
     * @param token the JWT string to validate
     * @return decoded {@link Claims} if valid
     * @throws JwtValidationException on any validation failure
     */
    public Claims validateToken(String token) {
        return parseAndValidateClaims(token);
    }

    // -----------------------------------------------------------------------
    // Private helpers
    // -----------------------------------------------------------------------

    private Claims parseAndValidateClaims(String token) {
        if (token == null || token.isBlank()) {
            throw new JwtValidationException("401: Token is missing or empty");
        }

        Claims claims;
        try {
            claims = Jwts.parser()
                    .verifyWith((javax.crypto.SecretKey) signingKey)
                    .build()
                    .parseSignedClaims(token)
                    .getPayload();
        } catch (ExpiredJwtException e) {
            throw new JwtValidationException("401: Token has expired", e);
        } catch (JwtException e) {
            throw new JwtValidationException("401: Invalid token: " + e.getMessage(), e);
        }

        // Reject tokens with incorrect payload formats (Task 1 AC3)
        if (claims.get("userId") == null) {
            throw new JwtValidationException("401: Token payload missing required userId claim");
        }

        return claims;
    }

    // -----------------------------------------------------------------------
    // Exception type
    // -----------------------------------------------------------------------

    /**
     * Thrown when JWT validation fails (maps to HTTP 401 Unauthorized).
     */
    public static class JwtValidationException extends RuntimeException {
        public JwtValidationException(String message) {
            super(message);
        }

        public JwtValidationException(String message, Throwable cause) {
            super(message, cause);
        }
    }
}
