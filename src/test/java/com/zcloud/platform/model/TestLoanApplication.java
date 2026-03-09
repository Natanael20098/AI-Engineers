package com.zcloud.platform.model;

import com.zcloud.platform.util.LoanValidator;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

/**
 * Unit tests for {@link LoanApplication}.
 *
 * <p>Verifies:
 * <ul>
 *   <li>Lifecycle state transitions (PENDING → APPROVED/REJECTED → DISBURSED).</li>
 *   <li>Delegation of calculations to {@code LoanCalculator}.</li>
 *   <li>Delegation of validation to {@code LoanValidator}.</li>
 *   <li>Illegal transition guards.</li>
 * </ul>
 */
class TestLoanApplication {

    private LoanApplication loan;

    @BeforeEach
    void setUp() {
        loan = new LoanApplication("applicant-001", 10_000.0, 12, 5.0);
    }

    // -----------------------------------------------------------------------
    // Construction & initial state
    // -----------------------------------------------------------------------

    @Test
    void newLoan_hasPendingStatus() {
        assertEquals(LoanApplication.Status.PENDING, loan.getStatus());
    }

    @Test
    void newLoan_hasGeneratedId() {
        assertNotNull(loan.getId());
        assertFalse(loan.getId().isBlank());
    }

    @Test
    void newLoan_hasCreatedAt() {
        assertNotNull(loan.getCreatedAt());
    }

    @Test
    void newLoan_storesFields() {
        assertEquals("applicant-001", loan.getApplicantId());
        assertEquals(10_000.0, loan.getAmount());
        assertEquals(12, loan.getTermMonths());
        assertEquals(5.0, loan.getAnnualInterestRate());
    }

    // -----------------------------------------------------------------------
    // Validation delegation
    // -----------------------------------------------------------------------

    @Test
    void constructor_rejectsNullApplicantId() {
        assertThrows(
                LoanValidator.LoanValidationException.class,
                () -> new LoanApplication(null, 1_000.0, 12, 5.0));
    }

    @Test
    void constructor_rejectsBlankApplicantId() {
        assertThrows(
                LoanValidator.LoanValidationException.class,
                () -> new LoanApplication("  ", 1_000.0, 12, 5.0));
    }

    @Test
    void constructor_rejectsTooSmallAmount() {
        assertThrows(
                LoanValidator.LoanValidationException.class,
                () -> new LoanApplication("applicant-001", 50.0, 12, 5.0));
    }

    @Test
    void constructor_rejectsTooLargeAmount() {
        assertThrows(
                LoanValidator.LoanValidationException.class,
                () -> new LoanApplication("applicant-001", 20_000_000.0, 12, 5.0));
    }

    @Test
    void constructor_rejectsZeroTermMonths() {
        assertThrows(
                LoanValidator.LoanValidationException.class,
                () -> new LoanApplication("applicant-001", 1_000.0, 0, 5.0));
    }

    @Test
    void constructor_rejectsNegativeInterestRate() {
        assertThrows(
                LoanValidator.LoanValidationException.class,
                () -> new LoanApplication("applicant-001", 1_000.0, 12, -1.0));
    }

    @Test
    void constructor_acceptsZeroInterestRate() {
        LoanApplication zeroRate = new LoanApplication("applicant-001", 1_000.0, 12, 0.0);
        assertEquals(0.0, zeroRate.getAnnualInterestRate());
    }

    // -----------------------------------------------------------------------
    // Lifecycle: approve
    // -----------------------------------------------------------------------

    @Test
    void approve_transitionsToApproved() {
        loan.approve();
        assertEquals(LoanApplication.Status.APPROVED, loan.getStatus());
    }

    @Test
    void approve_throwsWhenAlreadyApproved() {
        loan.approve();
        assertThrows(IllegalStateException.class, () -> loan.approve());
    }

    @Test
    void approve_throwsWhenRejected() {
        loan.reject();
        assertThrows(IllegalStateException.class, () -> loan.approve());
    }

    // -----------------------------------------------------------------------
    // Lifecycle: reject
    // -----------------------------------------------------------------------

    @Test
    void reject_transitionsToRejected() {
        loan.reject();
        assertEquals(LoanApplication.Status.REJECTED, loan.getStatus());
    }

    @Test
    void reject_throwsWhenAlreadyRejected() {
        loan.reject();
        assertThrows(IllegalStateException.class, () -> loan.reject());
    }

    @Test
    void reject_throwsWhenApproved() {
        loan.approve();
        assertThrows(IllegalStateException.class, () -> loan.reject());
    }

    // -----------------------------------------------------------------------
    // Lifecycle: disburse
    // -----------------------------------------------------------------------

    @Test
    void disburse_transitionsToDisbursed() {
        loan.approve();
        loan.disburse();
        assertEquals(LoanApplication.Status.DISBURSED, loan.getStatus());
    }

    @Test
    void disburse_throwsWhenPending() {
        assertThrows(IllegalStateException.class, () -> loan.disburse());
    }

    @Test
    void disburse_throwsWhenRejected() {
        loan.reject();
        assertThrows(IllegalStateException.class, () -> loan.disburse());
    }

    @Test
    void disburse_throwsWhenAlreadyDisbursed() {
        loan.approve();
        loan.disburse();
        assertThrows(IllegalStateException.class, () -> loan.disburse());
    }

    // -----------------------------------------------------------------------
    // Calculation delegation
    // -----------------------------------------------------------------------

    @Test
    void getMonthlyPayment_returnsPositiveValue() {
        double payment = loan.getMonthlyPayment();
        assertTrue(payment > 0, "Monthly payment must be positive");
    }

    @Test
    void getMonthlyPayment_zeroRateDividesPrincipalEvenly() {
        LoanApplication zeroRate = new LoanApplication("applicant-001", 1_200.0, 12, 0.0);
        assertEquals(100.0, zeroRate.getMonthlyPayment(), 0.01);
    }

    @Test
    void getTotalRepayment_isGreaterThanOrEqualToPrincipal() {
        assertTrue(loan.getTotalRepayment() >= loan.getAmount());
    }

    @Test
    void getTotalRepayment_equalsMonthlyPaymentTimesTermMonths() {
        double expected = loan.getMonthlyPayment() * loan.getTermMonths();
        assertEquals(expected, loan.getTotalRepayment(), 0.01);
    }

    @Test
    void getTotalInterest_equalsTotalRepaymentMinusPrincipal() {
        double expected = loan.getTotalRepayment() - loan.getAmount();
        assertEquals(expected, loan.getTotalInterest(), 0.01);
    }

    @Test
    void getTotalInterest_isZeroForZeroRate() {
        LoanApplication zeroRate = new LoanApplication("applicant-001", 1_200.0, 12, 0.0);
        assertEquals(0.0, zeroRate.getTotalInterest(), 0.01);
    }

    // -----------------------------------------------------------------------
    // Each loan has a unique ID
    // -----------------------------------------------------------------------

    @Test
    void twoLoans_haveDifferentIds() {
        LoanApplication another = new LoanApplication("applicant-002", 5_000.0, 24, 3.5);
        assertNotEquals(loan.getId(), another.getId());
    }
}
