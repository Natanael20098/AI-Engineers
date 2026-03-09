package com.zcloud.platform.util;

/**
 * LoanCalculator – reusable utility for loan financial computations.
 *
 * <p>Extracted from {@code LoanApplication} to centralise all calculation logic,
 * eliminating duplication and enabling independent testing.
 */
public class LoanCalculator {

    private LoanCalculator() {
        // utility class – do not instantiate
    }

    /**
     * Calculate the fixed monthly payment using the standard annuity formula.
     *
     * <p>Formula: {@code P * r / (1 - (1 + r)^-n)}
     * where {@code r = annualRate / 12 / 100} and {@code n = termMonths}.
     *
     * <p>When {@code annualRate} is 0 the payment is simply {@code principal / termMonths}.
     *
     * @param principal   loan principal in the currency of account (must be &gt; 0)
     * @param annualRate  annual interest rate as a percentage, e.g. {@code 5.0} for 5%
     * @param termMonths  number of monthly repayment periods (must be &gt; 0)
     * @return monthly payment amount, rounded to two decimal places
     */
    public static double calculateMonthlyPayment(double principal, double annualRate, int termMonths) {
        if (annualRate == 0.0) {
            return round2(principal / termMonths);
        }
        double monthlyRate = annualRate / 12.0 / 100.0;
        double factor = Math.pow(1 + monthlyRate, termMonths);
        return round2(principal * monthlyRate * factor / (factor - 1));
    }

    /**
     * Calculate the total amount repaid over the full loan term.
     *
     * @param monthlyPayment monthly instalment amount
     * @param termMonths     number of monthly repayment periods
     * @return total repayment amount, rounded to two decimal places
     */
    public static double calculateTotalRepayment(double monthlyPayment, int termMonths) {
        return round2(monthlyPayment * termMonths);
    }

    /**
     * Calculate the total interest paid over the full loan term.
     *
     * @param totalRepayment total amount repaid (principal + interest)
     * @param principal      original loan principal
     * @return total interest paid, rounded to two decimal places
     */
    public static double calculateTotalInterest(double totalRepayment, double principal) {
        return round2(totalRepayment - principal);
    }

    /**
     * Round a value to two decimal places using half-up rounding.
     *
     * @param value the value to round
     * @return value rounded to two decimal places
     */
    static double round2(double value) {
        return Math.round(value * 100.0) / 100.0;
    }
}
