package com.zcloud.platform.util;

import io.jsonwebtoken.Claims;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

/**
 * Unit tests for {@link SecurityUtils}.
 *
 * Covers Task 5 acceptance criteria:
 * - AC1: Role-based access checks return true for authorized roles.
 * - AC2: Test coverage includes 100% of new methods.
 * - AC3: No deprecated methods remain in usage.
 */
class TestSecurityUtils {

    private static final String SECRET =
            "test-secret-key-must-be-at-least-32-bytes!!";

    private JwtUtil jwtUtil;
    private SecurityUtils securityUtils;

    @BeforeEach
    void setUp() {
        jwtUtil = new JwtUtil(SECRET, 60_000L);
        securityUtils = new SecurityUtils(jwtUtil);
    }

    // -----------------------------------------------------------------------
    // hasRole – AC1
    // -----------------------------------------------------------------------

    @Test
    void hasRole_returnsTrueForAuthorizedRole() {
        String token = jwtUtil.generateToken("user-001", List.of("ROLE_USER", "ROLE_ADMIN"));
        assertTrue(securityUtils.hasRole(token, "ROLE_ADMIN"));
    }

    @Test
    void hasRole_returnsFalseForMissingRole() {
        String token = jwtUtil.generateToken("user-001", List.of("ROLE_USER"));
        assertFalse(securityUtils.hasRole(token, "ROLE_ADMIN"));
    }

    @Test
    void hasRole_returnsFalseForInvalidToken() {
        assertFalse(securityUtils.hasRole("invalid.token", "ROLE_USER"));
    }

    // -----------------------------------------------------------------------
    // hasRoleInClaims
    // -----------------------------------------------------------------------

    @Test
    void hasRoleInClaims_returnsTrueForAuthorizedRole() {
        String token = jwtUtil.generateToken("user-001", List.of("ROLE_ADMIN"));
        Claims claims = jwtUtil.validateToken(token);
        assertTrue(securityUtils.hasRoleInClaims(claims, "ROLE_ADMIN"));
    }

    @Test
    void hasRoleInClaims_returnsFalseForMissingRole() {
        String token = jwtUtil.generateToken("user-001", List.of("ROLE_USER"));
        Claims claims = jwtUtil.validateToken(token);
        assertFalse(securityUtils.hasRoleInClaims(claims, "ROLE_ADMIN"));
    }

    @Test
    void hasRoleInClaims_returnsFalseForNullClaims() {
        assertFalse(securityUtils.hasRoleInClaims(null, "ROLE_ADMIN"));
    }

    // -----------------------------------------------------------------------
    // hasAllRoles
    // -----------------------------------------------------------------------

    @Test
    void hasAllRoles_returnsTrueWhenAllRolesPresent() {
        String token = jwtUtil.generateToken("user-001",
                List.of("ROLE_USER", "ROLE_ADMIN", "ROLE_MANAGER"));
        assertTrue(securityUtils.hasAllRoles(token, List.of("ROLE_USER", "ROLE_ADMIN")));
    }

    @Test
    void hasAllRoles_returnsFalseWhenAnyRoleMissing() {
        String token = jwtUtil.generateToken("user-001", List.of("ROLE_USER"));
        assertFalse(securityUtils.hasAllRoles(token, List.of("ROLE_USER", "ROLE_ADMIN")));
    }

    @Test
    void hasAllRoles_returnsTrueForEmptyRequiredList() {
        String token = jwtUtil.generateToken("user-001", List.of("ROLE_USER"));
        assertTrue(securityUtils.hasAllRoles(token, List.of()));
    }

    // -----------------------------------------------------------------------
    // hasAnyRole
    // -----------------------------------------------------------------------

    @Test
    void hasAnyRole_returnsTrueWhenAnyRolePresent() {
        String token = jwtUtil.generateToken("user-001", List.of("ROLE_USER"));
        assertTrue(securityUtils.hasAnyRole(token, List.of("ROLE_ADMIN", "ROLE_USER")));
    }

    @Test
    void hasAnyRole_returnsFalseWhenNoRolePresent() {
        String token = jwtUtil.generateToken("user-001", List.of("ROLE_USER"));
        assertFalse(securityUtils.hasAnyRole(token, List.of("ROLE_ADMIN", "ROLE_MANAGER")));
    }

    @Test
    void hasAnyRole_returnsFalseForEmptyAllowedList() {
        String token = jwtUtil.generateToken("user-001", List.of("ROLE_USER"));
        assertFalse(securityUtils.hasAnyRole(token, List.of()));
    }

    // -----------------------------------------------------------------------
    // Access attempt tracking
    // -----------------------------------------------------------------------

    @Test
    void recordFailedAttempt_incrementsCounter() {
        securityUtils.recordFailedAttempt("alice");
        securityUtils.recordFailedAttempt("alice");
        assertEquals(2, securityUtils.getFailedAttemptCount("alice"));
    }

    @Test
    void resetFailedAttempts_clearsCounter() {
        securityUtils.recordFailedAttempt("alice");
        securityUtils.resetFailedAttempts("alice");
        assertEquals(0, securityUtils.getFailedAttemptCount("alice"));
    }

    @Test
    void isLockedOut_returnsTrueAfterMaxAttempts() {
        securityUtils.recordFailedAttempt("bob");
        securityUtils.recordFailedAttempt("bob");
        securityUtils.recordFailedAttempt("bob");
        assertTrue(securityUtils.isLockedOut("bob", 3));
    }

    @Test
    void isLockedOut_returnsFalseBeforeMaxAttempts() {
        securityUtils.recordFailedAttempt("carol");
        assertFalse(securityUtils.isLockedOut("carol", 3));
    }

    @Test
    void getFailedAttemptCount_returnsZeroForUnknownIdentifier() {
        assertEquals(0, securityUtils.getFailedAttemptCount("unknown"));
    }
}
