package com.zcloud.platform;

import com.zcloud.platform.model.LoanApplication;
import com.zcloud.platform.util.LoanCalculator;
import com.zcloud.platform.util.LoanValidator;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

/**
 * LoanApplicationModulesTest – comprehensive unit tests for all modules
 * introduced by the LoanApplication refactor:
 *
 * <ul>
 *   <li>{@link LoanCalculator}  – financial computation utility</li>
 *   <li>{@link LoanValidator}   – field validation utility</li>
 *   <li>{@link LoanApplication} – domain entity / lifecycle state machine</li>
 * </ul>
 *
 * <p>Testing patterns follow {@code TestLoanApplication}, {@code TestJwtUtil},
 * and {@code TestSecurityUtils} found in this test suite.
 *
 * <p>Each nested class is isolated: it sets up its own fixtures and asserts
 * only against the module under test.  No test has side-effects on another.
 */
class LoanApplicationModulesTest {

    // =========================================================================
    // MODULE 1: LoanCalculator
    // =========================================================================

    /**
     * Tests for {@link LoanCalculator}.
     *
     * <p>Covers: {@code calculateMonthlyPayment}, {@code calculateTotalRepayment},
     * {@code calculateTotalInterest}, and {@code round2} (package-private, tested
     * indirectly through the public API).
     */
    @Nested
    class LoanCalculatorTests {

        // ------------------------------------------------------------------
        // calculateMonthlyPayment
        // ------------------------------------------------------------------

        @Test
        void monthlyPayment_withTypicalInterestRate_matchesAnnuityFormula() {
            // $10 000 at 5% annual over 12 months → ≈ $856.07
            double payment = LoanCalculator.calculateMonthlyPayment(10_000.0, 5.0, 12);
            assertEquals(856.07, payment, 0.01,
                    "Monthly payment should match standard annuity formula result");
        }

        @Test
        void monthlyPayment_zeroInterestRate_dividesPrincipalEvenlyByTerm() {
            // Zero rate: simply principal / termMonths
            double payment = LoanCalculator.calculateMonthlyPayment(1_200.0, 0.0, 12);
            assertEquals(100.0, payment, 0.001,
                    "Zero-rate monthly payment should equal principal / termMonths");
        }

        @Test
        void monthlyPayment_singleMonth_zeroRate_equalsPrincipal() {
            double payment = LoanCalculator.calculateMonthlyPayment(5_000.0, 0.0, 1);
            assertEquals(5_000.0, payment, 0.001,
                    "Single-month zero-rate payment should equal the principal");
        }

        @Test
        void monthlyPayment_isAlwaysPositive() {
            double payment = LoanCalculator.calculateMonthlyPayment(50_000.0, 8.5, 60);
            assertTrue(payment > 0, "Monthly payment must be positive");
        }

        @Test
        void monthlyPayment_highInterestRate_isHigherThanLowRate() {
            double low  = LoanCalculator.calculateMonthlyPayment(10_000.0, 1.0, 12);
            double high = LoanCalculator.calculateMonthlyPayment(10_000.0, 20.0, 12);
            assertTrue(high > low,
                    "Higher interest rate must produce a higher monthly payment");
        }

        @Test
        void monthlyPayment_longerTerm_isLowerThanShorterTerm() {
            double short12 = LoanCalculator.calculateMonthlyPayment(10_000.0, 5.0, 12);
            double long24  = LoanCalculator.calculateMonthlyPayment(10_000.0, 5.0, 24);
            assertTrue(long24 < short12,
                    "Longer repayment term must produce a lower monthly payment");
        }

        @Test
        void monthlyPayment_largeAmount_returnsProportionalResult() {
            // Scaling principal should scale the payment by the same factor
            double base   = LoanCalculator.calculateMonthlyPayment(10_000.0, 5.0, 12);
            double scaled = LoanCalculator.calculateMonthlyPayment(100_000.0, 5.0, 12);
            assertEquals(base * 10, scaled, 0.05,
                    "Monthly payment should scale proportionally with the principal");
        }

        @Test
        void monthlyPayment_isRoundedToTwoDecimalPlaces() {
            double payment = LoanCalculator.calculateMonthlyPayment(7_777.0, 3.33, 18);
            // Verify at most 2 decimal places by checking round-trip
            double rounded = Math.round(payment * 100.0) / 100.0;
            assertEquals(rounded, payment, 0.0001,
                    "Result should already be rounded to 2 decimal places");
        }

        // ------------------------------------------------------------------
        // calculateTotalRepayment
        // ------------------------------------------------------------------

        @Test
        void totalRepayment_equalsMonthlyPaymentTimesTermMonths() {
            double monthly = 856.07;
            int term = 12;
            double total = LoanCalculator.calculateTotalRepayment(monthly, term);
            assertEquals(monthly * term, total, 0.01,
                    "Total repayment must equal monthlyPayment × termMonths");
        }

        @Test
        void totalRepayment_singlePayment_equalsThatPayment() {
            double total = LoanCalculator.calculateTotalRepayment(1_500.0, 1);
            assertEquals(1_500.0, total, 0.001,
                    "Single-period total repayment should equal the single payment");
        }

        @Test
        void totalRepayment_isRoundedToTwoDecimalPlaces() {
            double total = LoanCalculator.calculateTotalRepayment(333.33, 3);
            double rounded = Math.round(total * 100.0) / 100.0;
            assertEquals(rounded, total, 0.0001,
                    "Total repayment should be rounded to 2 decimal places");
        }

        @Test
        void totalRepayment_isAtLeastPrincipalForPositiveRate() {
            double principal  = 10_000.0;
            double monthly    = LoanCalculator.calculateMonthlyPayment(principal, 5.0, 12);
            double total      = LoanCalculator.calculateTotalRepayment(monthly, 12);
            assertTrue(total >= principal,
                    "Total repayment must be at least as large as the original principal");
        }

        // ------------------------------------------------------------------
        // calculateTotalInterest
        // ------------------------------------------------------------------

        @Test
        void totalInterest_equalsTotalRepaymentMinusPrincipal() {
            double totalRepayment = 10_272.84;
            double principal      = 10_000.0;
            double interest       = LoanCalculator.calculateTotalInterest(totalRepayment, principal);
            assertEquals(272.84, interest, 0.01,
                    "Total interest must equal totalRepayment − principal");
        }

        @Test
        void totalInterest_zeroRateLoan_isZero() {
            // $1 200 at 0%, 12 months → monthly = $100, total = $1 200, interest = $0
            double principal = 1_200.0;
            double monthly   = LoanCalculator.calculateMonthlyPayment(principal, 0.0, 12);
            double total     = LoanCalculator.calculateTotalRepayment(monthly, 12);
            double interest  = LoanCalculator.calculateTotalInterest(total, principal);
            assertEquals(0.0, interest, 0.01,
                    "Zero-rate loan should carry zero total interest");
        }

        @Test
        void totalInterest_isNonNegative() {
            double principal = 5_000.0;
            double monthly   = LoanCalculator.calculateMonthlyPayment(principal, 7.0, 36);
            double total     = LoanCalculator.calculateTotalRepayment(monthly, 36);
            double interest  = LoanCalculator.calculateTotalInterest(total, principal);
            assertTrue(interest >= 0,
                    "Total interest must be non-negative");
        }

        @Test
        void totalInterest_isRoundedToTwoDecimalPlaces() {
            double interest = LoanCalculator.calculateTotalInterest(10_272.84, 10_000.0);
            double rounded  = Math.round(interest * 100.0) / 100.0;
            assertEquals(rounded, interest, 0.0001,
                    "Total interest should be rounded to 2 decimal places");
        }

        // ------------------------------------------------------------------
        // round2 (package-private – tested indirectly through public API)
        // ------------------------------------------------------------------

        @Test
        void monthlyPayment_resultIsConsistentWithDirectRounding() {
            // round2 should use half-up rounding; verify via known values
            double payment = LoanCalculator.calculateMonthlyPayment(1_000.0, 0.0, 3);
            // 1000 / 3 = 333.333… → rounds to 333.33
            assertEquals(333.33, payment, 0.0001,
                    "round2 should truncate to 2 decimal places with half-up rounding");
        }
    }

    // =========================================================================
    // MODULE 2: LoanValidator
    // =========================================================================

    /**
     * Tests for {@link LoanValidator}.
     *
     * <p>Covers: {@code validateAmount}, {@code validateTermMonths},
     * {@code validateInterestRate}, {@code validateApplicantId}, and
     * the nested {@link LoanValidator.LoanValidationException}.
     */
    @Nested
    class LoanValidatorTests {

        // ------------------------------------------------------------------
        // validateAmount – happy path
        // ------------------------------------------------------------------

        @Test
        void validateAmount_typicalAmount_doesNotThrow() {
            assertDoesNotThrow(() -> LoanValidator.validateAmount(10_000.0),
                    "Typical loan amount should be accepted");
        }

        @Test
        void validateAmount_exactMinimumBoundary_doesNotThrow() {
            assertDoesNotThrow(() -> LoanValidator.validateAmount(100.0),
                    "Exact minimum amount (100.0) should be accepted");
        }

        @Test
        void validateAmount_exactMaximumBoundary_doesNotThrow() {
            assertDoesNotThrow(() -> LoanValidator.validateAmount(10_000_000.0),
                    "Exact maximum amount (10,000,000.0) should be accepted");
        }

        // ------------------------------------------------------------------
        // validateAmount – invalid inputs
        // ------------------------------------------------------------------

        @Test
        void validateAmount_justBelowMinimum_throwsLoanValidationException() {
            assertThrows(LoanValidator.LoanValidationException.class,
                    () -> LoanValidator.validateAmount(99.99),
                    "Amount just below minimum must throw LoanValidationException");
        }

        @Test
        void validateAmount_zero_throwsLoanValidationException() {
            assertThrows(LoanValidator.LoanValidationException.class,
                    () -> LoanValidator.validateAmount(0.0),
                    "Zero amount must throw LoanValidationException");
        }

        @Test
        void validateAmount_negativeValue_throwsLoanValidationException() {
            assertThrows(LoanValidator.LoanValidationException.class,
                    () -> LoanValidator.validateAmount(-500.0),
                    "Negative amount must throw LoanValidationException");
        }

        @Test
        void validateAmount_justAboveMaximum_throwsLoanValidationException() {
            assertThrows(LoanValidator.LoanValidationException.class,
                    () -> LoanValidator.validateAmount(10_000_000.01),
                    "Amount just above maximum must throw LoanValidationException");
        }

        @Test
        void validateAmount_exceptionMessageContainsReceivedValue() {
            LoanValidator.LoanValidationException ex = assertThrows(
                    LoanValidator.LoanValidationException.class,
                    () -> LoanValidator.validateAmount(50.0));
            assertTrue(ex.getMessage().contains("50.0"),
                    "Exception message should include the invalid amount");
        }

        // ------------------------------------------------------------------
        // validateTermMonths – happy path
        // ------------------------------------------------------------------

        @Test
        void validateTermMonths_typicalTerm_doesNotThrow() {
            assertDoesNotThrow(() -> LoanValidator.validateTermMonths(24),
                    "Typical term (24 months) should be accepted");
        }

        @Test
        void validateTermMonths_exactMinimumBoundary_doesNotThrow() {
            assertDoesNotThrow(() -> LoanValidator.validateTermMonths(1),
                    "Exact minimum term (1 month) should be accepted");
        }

        @Test
        void validateTermMonths_exactMaximumBoundary_doesNotThrow() {
            assertDoesNotThrow(() -> LoanValidator.validateTermMonths(480),
                    "Exact maximum term (480 months) should be accepted");
        }

        // ------------------------------------------------------------------
        // validateTermMonths – invalid inputs
        // ------------------------------------------------------------------

        @Test
        void validateTermMonths_zero_throwsLoanValidationException() {
            assertThrows(LoanValidator.LoanValidationException.class,
                    () -> LoanValidator.validateTermMonths(0),
                    "Zero term must throw LoanValidationException");
        }

        @Test
        void validateTermMonths_negativeValue_throwsLoanValidationException() {
            assertThrows(LoanValidator.LoanValidationException.class,
                    () -> LoanValidator.validateTermMonths(-6),
                    "Negative term must throw LoanValidationException");
        }

        @Test
        void validateTermMonths_justAboveMaximum_throwsLoanValidationException() {
            assertThrows(LoanValidator.LoanValidationException.class,
                    () -> LoanValidator.validateTermMonths(481),
                    "Term exceeding maximum (480) must throw LoanValidationException");
        }

        @Test
        void validateTermMonths_exceptionMessageContainsReceivedValue() {
            LoanValidator.LoanValidationException ex = assertThrows(
                    LoanValidator.LoanValidationException.class,
                    () -> LoanValidator.validateTermMonths(0));
            assertTrue(ex.getMessage().contains("0"),
                    "Exception message should include the invalid term value");
        }

        // ------------------------------------------------------------------
        // validateInterestRate – happy path
        // ------------------------------------------------------------------

        @Test
        void validateInterestRate_typicalRate_doesNotThrow() {
            assertDoesNotThrow(() -> LoanValidator.validateInterestRate(5.0),
                    "Typical interest rate (5.0%) should be accepted");
        }

        @Test
        void validateInterestRate_zeroRate_doesNotThrow() {
            assertDoesNotThrow(() -> LoanValidator.validateInterestRate(0.0),
                    "Zero interest rate should be accepted (interest-free loan)");
        }

        @Test
        void validateInterestRate_exactMaximumBoundary_doesNotThrow() {
            assertDoesNotThrow(() -> LoanValidator.validateInterestRate(100.0),
                    "Exact maximum interest rate (100.0%) should be accepted");
        }

        // ------------------------------------------------------------------
        // validateInterestRate – invalid inputs
        // ------------------------------------------------------------------

        @Test
        void validateInterestRate_negativeRate_throwsLoanValidationException() {
            assertThrows(LoanValidator.LoanValidationException.class,
                    () -> LoanValidator.validateInterestRate(-0.01),
                    "Negative interest rate must throw LoanValidationException");
        }

        @Test
        void validateInterestRate_justAboveMaximum_throwsLoanValidationException() {
            assertThrows(LoanValidator.LoanValidationException.class,
                    () -> LoanValidator.validateInterestRate(100.01),
                    "Rate above 100% must throw LoanValidationException");
        }

        @Test
        void validateInterestRate_exceptionMessageContainsReceivedValue() {
            LoanValidator.LoanValidationException ex = assertThrows(
                    LoanValidator.LoanValidationException.class,
                    () -> LoanValidator.validateInterestRate(-5.0));
            assertTrue(ex.getMessage().contains("-5.0"),
                    "Exception message should include the invalid rate value");
        }

        // ------------------------------------------------------------------
        // validateApplicantId – happy path
        // ------------------------------------------------------------------

        @Test
        void validateApplicantId_typicalId_doesNotThrow() {
            assertDoesNotThrow(() -> LoanValidator.validateApplicantId("applicant-123"),
                    "Typical applicant ID should be accepted");
        }

        @Test
        void validateApplicantId_singleCharacter_doesNotThrow() {
            assertDoesNotThrow(() -> LoanValidator.validateApplicantId("X"),
                    "Single-character applicant ID should be accepted");
        }

        @Test
        void validateApplicantId_numericId_doesNotThrow() {
            assertDoesNotThrow(() -> LoanValidator.validateApplicantId("42"),
                    "Numeric string applicant ID should be accepted");
        }

        // ------------------------------------------------------------------
        // validateApplicantId – invalid inputs
        // ------------------------------------------------------------------

        @Test
        void validateApplicantId_null_throwsLoanValidationException() {
            assertThrows(LoanValidator.LoanValidationException.class,
                    () -> LoanValidator.validateApplicantId(null),
                    "Null applicant ID must throw LoanValidationException");
        }

        @Test
        void validateApplicantId_emptyString_throwsLoanValidationException() {
            assertThrows(LoanValidator.LoanValidationException.class,
                    () -> LoanValidator.validateApplicantId(""),
                    "Empty applicant ID must throw LoanValidationException");
        }

        @Test
        void validateApplicantId_blankSpaces_throwsLoanValidationException() {
            assertThrows(LoanValidator.LoanValidationException.class,
                    () -> LoanValidator.validateApplicantId("   "),
                    "Blank (whitespace-only) applicant ID must throw LoanValidationException");
        }

        @Test
        void validateApplicantId_tabOnly_throwsLoanValidationException() {
            assertThrows(LoanValidator.LoanValidationException.class,
                    () -> LoanValidator.validateApplicantId("\t"),
                    "Tab-only applicant ID must throw LoanValidationException");
        }

        // ------------------------------------------------------------------
        // LoanValidationException
        // ------------------------------------------------------------------

        @Test
        void loanValidationException_extendsRuntimeException() {
            LoanValidator.LoanValidationException ex =
                    new LoanValidator.LoanValidationException("test message");
            assertInstanceOf(RuntimeException.class, ex,
                    "LoanValidationException must extend RuntimeException");
        }

        @Test
        void loanValidationException_hasNonNullNonBlankMessage() {
            LoanValidator.LoanValidationException ex = assertThrows(
                    LoanValidator.LoanValidationException.class,
                    () -> LoanValidator.validateAmount(0.0));
            assertNotNull(ex.getMessage(),
                    "Exception message must not be null");
            assertFalse(ex.getMessage().isBlank(),
                    "Exception message must not be blank");
        }
    }

    // =========================================================================
    // MODULE 3: LoanApplication
    // =========================================================================

    /**
     * Tests for {@link LoanApplication}.
     *
     * <p>Covers: constructor validation, all getter accessors, the three lifecycle
     * transitions ({@code approve}, {@code reject}, {@code disburse}), illegal
     * state guards, and the three calculation-delegation methods
     * ({@code getMonthlyPayment}, {@code getTotalRepayment}, {@code getTotalInterest}).
     */
    @Nested
    class LoanApplicationTests {

        private LoanApplication loan;

        @BeforeEach
        void setUp() {
            loan = new LoanApplication("applicant-001", 10_000.0, 12, 5.0);
        }

        // ------------------------------------------------------------------
        // Constructor – valid construction and initial state
        // ------------------------------------------------------------------

        @Test
        void newLoan_initialStatusIsPending() {
            assertEquals(LoanApplication.Status.PENDING, loan.getStatus(),
                    "A newly created loan must be in PENDING status");
        }

        @Test
        void newLoan_hasNonNullNonBlankId() {
            assertNotNull(loan.getId(), "Loan ID must not be null");
            assertFalse(loan.getId().isBlank(), "Loan ID must not be blank");
        }

        @Test
        void newLoan_hasCreatedAtTimestamp() {
            assertNotNull(loan.getCreatedAt(), "createdAt must not be null");
        }

        @Test
        void newLoan_storesApplicantId() {
            assertEquals("applicant-001", loan.getApplicantId());
        }

        @Test
        void newLoan_storesAmount() {
            assertEquals(10_000.0, loan.getAmount());
        }

        @Test
        void newLoan_storesTermMonths() {
            assertEquals(12, loan.getTermMonths());
        }

        @Test
        void newLoan_storesAnnualInterestRate() {
            assertEquals(5.0, loan.getAnnualInterestRate());
        }

        @Test
        void twoLoans_alwaysHaveDifferentIds() {
            LoanApplication another = new LoanApplication("applicant-002", 5_000.0, 24, 3.5);
            assertNotEquals(loan.getId(), another.getId(),
                    "Each loan must receive a unique ID");
        }

        // ------------------------------------------------------------------
        // Constructor – validation delegation to LoanValidator
        // ------------------------------------------------------------------

        @Test
        void constructor_nullApplicantId_throwsLoanValidationException() {
            assertThrows(LoanValidator.LoanValidationException.class,
                    () -> new LoanApplication(null, 1_000.0, 12, 5.0),
                    "Null applicant ID must be rejected");
        }

        @Test
        void constructor_blankApplicantId_throwsLoanValidationException() {
            assertThrows(LoanValidator.LoanValidationException.class,
                    () -> new LoanApplication("  ", 1_000.0, 12, 5.0),
                    "Blank applicant ID must be rejected");
        }

        @Test
        void constructor_amountBelowMinimum_throwsLoanValidationException() {
            assertThrows(LoanValidator.LoanValidationException.class,
                    () -> new LoanApplication("app-1", 50.0, 12, 5.0),
                    "Amount below 100.0 must be rejected");
        }

        @Test
        void constructor_amountAboveMaximum_throwsLoanValidationException() {
            assertThrows(LoanValidator.LoanValidationException.class,
                    () -> new LoanApplication("app-1", 20_000_000.0, 12, 5.0),
                    "Amount above 10,000,000.0 must be rejected");
        }

        @Test
        void constructor_zeroTermMonths_throwsLoanValidationException() {
            assertThrows(LoanValidator.LoanValidationException.class,
                    () -> new LoanApplication("app-1", 1_000.0, 0, 5.0),
                    "Zero term months must be rejected");
        }

        @Test
        void constructor_negativeTermMonths_throwsLoanValidationException() {
            assertThrows(LoanValidator.LoanValidationException.class,
                    () -> new LoanApplication("app-1", 1_000.0, -3, 5.0),
                    "Negative term months must be rejected");
        }

        @Test
        void constructor_negativeInterestRate_throwsLoanValidationException() {
            assertThrows(LoanValidator.LoanValidationException.class,
                    () -> new LoanApplication("app-1", 1_000.0, 12, -1.0),
                    "Negative interest rate must be rejected");
        }

        @Test
        void constructor_zeroInterestRate_isAccepted() {
            LoanApplication zeroRate = new LoanApplication("app-1", 1_000.0, 12, 0.0);
            assertEquals(0.0, zeroRate.getAnnualInterestRate(),
                    "Zero interest rate is valid and must be stored");
        }

        @Test
        void constructor_maximumInterestRate_isAccepted() {
            LoanApplication maxRate = new LoanApplication("app-1", 1_000.0, 12, 100.0);
            assertEquals(100.0, maxRate.getAnnualInterestRate(),
                    "100% interest rate is the maximum and must be accepted");
        }

        // ------------------------------------------------------------------
        // Lifecycle – approve
        // ------------------------------------------------------------------

        @Test
        void approve_fromPending_transitionsToApproved() {
            loan.approve();
            assertEquals(LoanApplication.Status.APPROVED, loan.getStatus(),
                    "Approving a PENDING loan must move it to APPROVED");
        }

        @Test
        void approve_fromApproved_throwsIllegalStateException() {
            loan.approve();
            assertThrows(IllegalStateException.class, () -> loan.approve(),
                    "Approving an already-APPROVED loan must throw IllegalStateException");
        }

        @Test
        void approve_fromRejected_throwsIllegalStateException() {
            loan.reject();
            assertThrows(IllegalStateException.class, () -> loan.approve(),
                    "Approving a REJECTED loan must throw IllegalStateException");
        }

        @Test
        void approve_fromDisbursed_throwsIllegalStateException() {
            loan.approve();
            loan.disburse();
            assertThrows(IllegalStateException.class, () -> loan.approve(),
                    "Approving a DISBURSED loan must throw IllegalStateException");
        }

        @Test
        void approve_illegalStateExceptionMessageDescribesCurrentStatus() {
            loan.reject();
            IllegalStateException ex = assertThrows(
                    IllegalStateException.class, () -> loan.approve());
            assertTrue(ex.getMessage().contains("REJECTED"),
                    "Exception message should describe the current (REJECTED) status");
        }

        // ------------------------------------------------------------------
        // Lifecycle – reject
        // ------------------------------------------------------------------

        @Test
        void reject_fromPending_transitionsToRejected() {
            loan.reject();
            assertEquals(LoanApplication.Status.REJECTED, loan.getStatus(),
                    "Rejecting a PENDING loan must move it to REJECTED");
        }

        @Test
        void reject_fromRejected_throwsIllegalStateException() {
            loan.reject();
            assertThrows(IllegalStateException.class, () -> loan.reject(),
                    "Rejecting an already-REJECTED loan must throw IllegalStateException");
        }

        @Test
        void reject_fromApproved_throwsIllegalStateException() {
            loan.approve();
            assertThrows(IllegalStateException.class, () -> loan.reject(),
                    "Rejecting an APPROVED loan must throw IllegalStateException");
        }

        @Test
        void reject_fromDisbursed_throwsIllegalStateException() {
            loan.approve();
            loan.disburse();
            assertThrows(IllegalStateException.class, () -> loan.reject(),
                    "Rejecting a DISBURSED loan must throw IllegalStateException");
        }

        // ------------------------------------------------------------------
        // Lifecycle – disburse
        // ------------------------------------------------------------------

        @Test
        void disburse_fromApproved_transitionsToDisbursed() {
            loan.approve();
            loan.disburse();
            assertEquals(LoanApplication.Status.DISBURSED, loan.getStatus(),
                    "Disbursing an APPROVED loan must move it to DISBURSED");
        }

        @Test
        void disburse_fromPending_throwsIllegalStateException() {
            assertThrows(IllegalStateException.class, () -> loan.disburse(),
                    "Disbursing a PENDING loan must throw IllegalStateException");
        }

        @Test
        void disburse_fromRejected_throwsIllegalStateException() {
            loan.reject();
            assertThrows(IllegalStateException.class, () -> loan.disburse(),
                    "Disbursing a REJECTED loan must throw IllegalStateException");
        }

        @Test
        void disburse_fromDisbursed_throwsIllegalStateException() {
            loan.approve();
            loan.disburse();
            assertThrows(IllegalStateException.class, () -> loan.disburse(),
                    "Disbursing an already-DISBURSED loan must throw IllegalStateException");
        }

        @Test
        void disburse_illegalStateExceptionMessageDescribesCurrentStatus() {
            IllegalStateException ex = assertThrows(
                    IllegalStateException.class, () -> loan.disburse());
            assertTrue(ex.getMessage().contains("PENDING"),
                    "Exception message should describe the current (PENDING) status");
        }

        // ------------------------------------------------------------------
        // Calculation delegation – getMonthlyPayment
        // ------------------------------------------------------------------

        @Test
        void getMonthlyPayment_returnsPositiveValue() {
            assertTrue(loan.getMonthlyPayment() > 0,
                    "Monthly payment must be positive");
        }

        @Test
        void getMonthlyPayment_matchesLoanCalculatorResult() {
            double expected = LoanCalculator.calculateMonthlyPayment(
                    loan.getAmount(), loan.getAnnualInterestRate(), loan.getTermMonths());
            assertEquals(expected, loan.getMonthlyPayment(), 0.0001,
                    "getMonthlyPayment must delegate to LoanCalculator.calculateMonthlyPayment");
        }

        @Test
        void getMonthlyPayment_zeroRate_equalsPrincipalDividedByTerm() {
            LoanApplication zeroRate = new LoanApplication("app-1", 1_200.0, 12, 0.0);
            assertEquals(100.0, zeroRate.getMonthlyPayment(), 0.01,
                    "Zero-rate monthly payment should equal principal / termMonths");
        }

        // ------------------------------------------------------------------
        // Calculation delegation – getTotalRepayment
        // ------------------------------------------------------------------

        @Test
        void getTotalRepayment_isAtLeastPrincipal() {
            assertTrue(loan.getTotalRepayment() >= loan.getAmount(),
                    "Total repayment must be at least the loan principal");
        }

        @Test
        void getTotalRepayment_equalsMonthlyPaymentTimesTermMonths() {
            double expected = loan.getMonthlyPayment() * loan.getTermMonths();
            assertEquals(expected, loan.getTotalRepayment(), 0.01,
                    "getTotalRepayment must equal monthlyPayment × termMonths");
        }

        @Test
        void getTotalRepayment_zeroRate_equalsPrincipal() {
            LoanApplication zeroRate = new LoanApplication("app-1", 1_200.0, 12, 0.0);
            assertEquals(1_200.0, zeroRate.getTotalRepayment(), 0.01,
                    "Zero-rate total repayment should equal the principal");
        }

        // ------------------------------------------------------------------
        // Calculation delegation – getTotalInterest
        // ------------------------------------------------------------------

        @Test
        void getTotalInterest_equalsTotalRepaymentMinusPrincipal() {
            double expected = loan.getTotalRepayment() - loan.getAmount();
            assertEquals(expected, loan.getTotalInterest(), 0.01,
                    "getTotalInterest must equal totalRepayment − principal");
        }

        @Test
        void getTotalInterest_zeroRate_isZero() {
            LoanApplication zeroRate = new LoanApplication("app-1", 1_200.0, 12, 0.0);
            assertEquals(0.0, zeroRate.getTotalInterest(), 0.01,
                    "Zero-rate loan must carry zero total interest");
        }

        @Test
        void getTotalInterest_isNonNegative() {
            assertTrue(loan.getTotalInterest() >= 0,
                    "Total interest must be non-negative");
        }

        // ------------------------------------------------------------------
        // Full lifecycle smoke test
        // ------------------------------------------------------------------

        @Test
        void fullLifecycle_pendingApprovedDisbursed_completesWithoutError() {
            assertEquals(LoanApplication.Status.PENDING, loan.getStatus());
            loan.approve();
            assertEquals(LoanApplication.Status.APPROVED, loan.getStatus());
            loan.disburse();
            assertEquals(LoanApplication.Status.DISBURSED, loan.getStatus());
        }

        @Test
        void fullLifecycle_pendingRejected_completesWithoutError() {
            assertEquals(LoanApplication.Status.PENDING, loan.getStatus());
            loan.reject();
            assertEquals(LoanApplication.Status.REJECTED, loan.getStatus());
        }
    }
}
