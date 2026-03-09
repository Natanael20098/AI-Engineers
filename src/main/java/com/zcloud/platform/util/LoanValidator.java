package com.zcloud.platform.util;

/**
 * LoanValidator – reusable utility for validating loan application fields.
 *
 * <p>Extracted from {@code LoanApplication} to centralise all validation logic,
 * eliminating duplication and enabling independent testing.
 */
public class LoanValidator {

    /** Minimum allowed loan amount. */
    static final double MIN_AMOUNT = 100.0;

    /** Maximum allowed loan amount. */
    static final double MAX_AMOUNT = 10_000_000.0;

    /** Minimum allowed loan term in months. */
    static final int MIN_TERM_MONTHS = 1;

    /** Maximum allowed loan term in months (40 years). */
    static final int MAX_TERM_MONTHS = 480;

    /** Maximum allowed annual interest rate percentage. */
    static final double MAX_INTEREST_RATE = 100.0;

    private LoanValidator() {
        // utility class – do not instantiate
    }

    /**
     * Validate a loan amount.
     *
     * @param amount the requested loan amount
     * @throws LoanValidationException if the amount is outside the permitted range
     */
    public static void validateAmount(double amount) {
        if (amount < MIN_AMOUNT || amount > MAX_AMOUNT) {
            throw new LoanValidationException(
                    "Loan amount must be between " + MIN_AMOUNT + " and " + MAX_AMOUNT
                            + "; received: " + amount);
        }
    }

    /**
     * Validate a loan term expressed in months.
     *
     * @param termMonths the loan term
     * @throws LoanValidationException if the term is outside the permitted range
     */
    public static void validateTermMonths(int termMonths) {
        if (termMonths < MIN_TERM_MONTHS || termMonths > MAX_TERM_MONTHS) {
            throw new LoanValidationException(
                    "Term months must be between " + MIN_TERM_MONTHS + " and " + MAX_TERM_MONTHS
                            + "; received: " + termMonths);
        }
    }

    /**
     * Validate an annual interest rate.
     *
     * @param annualRate the annual interest rate as a percentage (e.g. {@code 5.0} for 5%)
     * @throws LoanValidationException if the rate is negative or exceeds the maximum
     */
    public static void validateInterestRate(double annualRate) {
        if (annualRate < 0.0 || annualRate > MAX_INTEREST_RATE) {
            throw new LoanValidationException(
                    "Interest rate must be between 0 and " + MAX_INTEREST_RATE
                            + "; received: " + annualRate);
        }
    }

    /**
     * Validate an applicant identifier.
     *
     * @param applicantId the applicant ID string
     * @throws LoanValidationException if the ID is null or blank
     */
    public static void validateApplicantId(String applicantId) {
        if (applicantId == null || applicantId.isBlank()) {
            throw new LoanValidationException("Applicant ID must not be null or blank");
        }
    }

    // -----------------------------------------------------------------------
    // Exception type
    // -----------------------------------------------------------------------

    /**
     * Thrown when a loan application field fails validation.
     */
    public static class LoanValidationException extends RuntimeException {
        public LoanValidationException(String message) {
            super(message);
        }
    }
}
