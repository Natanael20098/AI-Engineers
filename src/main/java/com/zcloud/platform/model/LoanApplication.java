package com.zcloud.platform.model;

import com.zcloud.platform.util.LoanCalculator;
import com.zcloud.platform.util.LoanValidator;

import java.time.Instant;
import java.util.UUID;

/**
 * LoanApplication – core domain entity representing a loan request.
 *
 * <p>All financial calculations are delegated to {@link LoanCalculator} and
 * all field-level validation to {@link LoanValidator}, keeping this class
 * focused solely on lifecycle state management.
 *
 * <p>Valid status transitions:
 * <pre>
 *   PENDING → APPROVED → DISBURSED
 *   PENDING → REJECTED
 * </pre>
 */
public class LoanApplication {

    // -----------------------------------------------------------------------
    // Status enum
    // -----------------------------------------------------------------------

    public enum Status {
        PENDING, APPROVED, REJECTED, DISBURSED
    }

    // -----------------------------------------------------------------------
    // Fields
    // -----------------------------------------------------------------------

    private final String id;
    private final String applicantId;
    private final double amount;
    private final int termMonths;
    private final double annualInterestRate;
    private Status status;
    private final Instant createdAt;

    // -----------------------------------------------------------------------
    // Constructor
    // -----------------------------------------------------------------------

    /**
     * Create a new LoanApplication in {@link Status#PENDING} state.
     *
     * <p>Validates all fields via {@link LoanValidator} before constructing the object.
     *
     * @param applicantId        unique identifier of the applicant
     * @param amount             requested loan amount (must be between 100 and 10,000,000)
     * @param termMonths         repayment period in months (must be between 1 and 480)
     * @param annualInterestRate annual interest rate as a percentage (0..100)
     * @throws LoanValidator.LoanValidationException if any field is invalid
     */
    public LoanApplication(String applicantId, double amount, int termMonths, double annualInterestRate) {
        LoanValidator.validateApplicantId(applicantId);
        LoanValidator.validateAmount(amount);
        LoanValidator.validateTermMonths(termMonths);
        LoanValidator.validateInterestRate(annualInterestRate);

        this.id = UUID.randomUUID().toString();
        this.applicantId = applicantId;
        this.amount = amount;
        this.termMonths = termMonths;
        this.annualInterestRate = annualInterestRate;
        this.status = Status.PENDING;
        this.createdAt = Instant.now();
    }

    // -----------------------------------------------------------------------
    // Lifecycle transitions
    // -----------------------------------------------------------------------

    /**
     * Approve the loan application.
     *
     * @throws IllegalStateException if the application is not in {@link Status#PENDING}
     */
    public void approve() {
        requireStatus(Status.PENDING, "approve");
        this.status = Status.APPROVED;
    }

    /**
     * Reject the loan application.
     *
     * @throws IllegalStateException if the application is not in {@link Status#PENDING}
     */
    public void reject() {
        requireStatus(Status.PENDING, "reject");
        this.status = Status.REJECTED;
    }

    /**
     * Mark the loan as disbursed.
     *
     * @throws IllegalStateException if the application is not in {@link Status#APPROVED}
     */
    public void disburse() {
        requireStatus(Status.APPROVED, "disburse");
        this.status = Status.DISBURSED;
    }

    // -----------------------------------------------------------------------
    // Financial calculations – delegated to LoanCalculator
    // -----------------------------------------------------------------------

    /**
     * Calculate and return the fixed monthly payment for this loan.
     *
     * @return monthly payment amount
     */
    public double getMonthlyPayment() {
        return LoanCalculator.calculateMonthlyPayment(amount, annualInterestRate, termMonths);
    }

    /**
     * Calculate and return the total amount repaid over the full term.
     *
     * @return total repayment amount
     */
    public double getTotalRepayment() {
        return LoanCalculator.calculateTotalRepayment(getMonthlyPayment(), termMonths);
    }

    /**
     * Calculate and return the total interest paid over the full term.
     *
     * @return total interest amount
     */
    public double getTotalInterest() {
        return LoanCalculator.calculateTotalInterest(getTotalRepayment(), amount);
    }

    // -----------------------------------------------------------------------
    // Accessors
    // -----------------------------------------------------------------------

    public String getId() {
        return id;
    }

    public String getApplicantId() {
        return applicantId;
    }

    public double getAmount() {
        return amount;
    }

    public int getTermMonths() {
        return termMonths;
    }

    public double getAnnualInterestRate() {
        return annualInterestRate;
    }

    public Status getStatus() {
        return status;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    // -----------------------------------------------------------------------
    // Private helpers
    // -----------------------------------------------------------------------

    private void requireStatus(Status required, String action) {
        if (this.status != required) {
            throw new IllegalStateException(
                    "Cannot " + action + " a loan that is " + this.status
                            + "; expected status: " + required);
        }
    }
}
