package com.zcloud.platform.util;

import io.jsonwebtoken.Claims;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

/**
 * Unit tests for {@link JwtUtil}.
 *
 * Covers Task 1 acceptance criteria:
 * - AC1: Token includes userId, roles, expiry.
 * - AC2: Expired tokens are successfully renewed.
 * - AC3: Tokens with incorrect payloads return 401 error.
 */
class TestJwtUtil {

    private static final String SECRET =
            "test-secret-key-must-be-at-least-32-bytes!!";
    private JwtUtil jwtUtil;

    @BeforeEach
    void setUp() {
        jwtUtil = new JwtUtil(SECRET, 60_000L); // 60-second expiry
    }

    // -----------------------------------------------------------------------
    // AC1 – Token includes userId, roles, expiry
    // -----------------------------------------------------------------------

    @Test
    void generateToken_includesUserId() {
        String token = jwtUtil.generateToken("user-001", List.of("ROLE_USER"));
        Claims claims = jwtUtil.validateToken(token);
        assertEquals("user-001", claims.get("userId", String.class));
    }

    @Test
    void generateToken_includesRoles() {
        String token = jwtUtil.generateToken("user-001", List.of("ROLE_USER", "ROLE_ADMIN"));
        Claims claims = jwtUtil.validateToken(token);
        @SuppressWarnings("unchecked")
        List<String> roles = (List<String>) claims.get("roles");
        assertNotNull(roles);
        assertTrue(roles.contains("ROLE_USER"));
        assertTrue(roles.contains("ROLE_ADMIN"));
    }

    @Test
    void generateToken_includesExpiry() {
        String token = jwtUtil.generateToken("user-001", List.of("ROLE_USER"));
        Claims claims = jwtUtil.validateToken(token);
        assertNotNull(claims.getExpiration());
        assertNotNull(claims.get("expiry", String.class));
    }

    // -----------------------------------------------------------------------
    // AC2 – Expired tokens are successfully renewed
    // -----------------------------------------------------------------------

    @Test
    void renewToken_renewsExpiredToken() throws InterruptedException {
        JwtUtil shortLived = new JwtUtil(SECRET, 1L); // 1 ms expiry
        String token = shortLived.generateToken("user-001", List.of("ROLE_USER"));
        Thread.sleep(10); // ensure expired

        String renewed = jwtUtil.renewToken(token);
        assertNotNull(renewed);

        Claims claims = jwtUtil.validateToken(renewed);
        assertEquals("user-001", claims.get("userId", String.class));
    }

    @Test
    void renewToken_preservesRoles() throws InterruptedException {
        JwtUtil shortLived = new JwtUtil(SECRET, 1L);
        String token = shortLived.generateToken("user-001", List.of("ROLE_ADMIN"));
        Thread.sleep(10);

        String renewed = jwtUtil.renewToken(token);
        Claims claims = jwtUtil.validateToken(renewed);
        @SuppressWarnings("unchecked")
        List<String> roles = (List<String>) claims.get("roles");
        assertTrue(roles.contains("ROLE_ADMIN"));
    }

    @Test
    void renewToken_throwsForGarbageToken() {
        assertThrows(
                JwtUtil.JwtValidationException.class,
                () -> jwtUtil.renewToken("not.a.valid.token")
        );
    }

    // -----------------------------------------------------------------------
    // AC3 – Tokens with incorrect payloads return 401 error
    // -----------------------------------------------------------------------

    @Test
    void validateToken_throwsForExpiredToken() throws InterruptedException {
        JwtUtil shortLived = new JwtUtil(SECRET, 1L);
        String token = shortLived.generateToken("user-001", List.of("ROLE_USER"));
        Thread.sleep(10);

        JwtUtil.JwtValidationException ex = assertThrows(
                JwtUtil.JwtValidationException.class,
                () -> jwtUtil.validateToken(token)
        );
        assertTrue(ex.getMessage().contains("401"));
    }

    @Test
    void validateToken_throwsForInvalidSignature() {
        String token = jwtUtil.generateToken("user-001", List.of("ROLE_USER"));
        String tampered = token.substring(0, token.lastIndexOf('.') + 1) + "TAMPERED";

        JwtUtil.JwtValidationException ex = assertThrows(
                JwtUtil.JwtValidationException.class,
                () -> jwtUtil.validateToken(tampered)
        );
        assertTrue(ex.getMessage().contains("401"));
    }

    @Test
    void validateToken_throwsForNullToken() {
        assertThrows(
                JwtUtil.JwtValidationException.class,
                () -> jwtUtil.validateToken((String) null)
        );
    }

    @Test
    void validateToken_withRoleCheck_passesForMatchingRole() {
        String token = jwtUtil.generateToken("user-001", List.of("ROLE_ADMIN"));
        assertDoesNotThrow(() -> jwtUtil.validateToken(token, "ROLE_ADMIN"));
    }

    @Test
    void validateToken_withRoleCheck_throwsForMissingRole() {
        String token = jwtUtil.generateToken("user-001", List.of("ROLE_USER"));
        JwtUtil.JwtValidationException ex = assertThrows(
                JwtUtil.JwtValidationException.class,
                () -> jwtUtil.validateToken(token, "ROLE_ADMIN")
        );
        assertTrue(ex.getMessage().contains("401"));
    }
}
