'use strict';
/**
 * PaymentProcessor.js – Payment processing microservice business logic.
 *
 * Handles payment initiation, confirmation, cancellation, and retrieval for
 * loan repayment processing within the Natanael platform.
 *
 * Designed to be stateless (no Express) so it can be unit-tested in isolation
 * and wrapped by app.js for HTTP exposure / supertest integration testing.
 */

const crypto = require('crypto');

// ---------------------------------------------------------------------------
// In-memory store (replaced by a real DB in production)
// ---------------------------------------------------------------------------

/** @type {Map<string, Object>} paymentId → payment record */
const _paymentStore = new Map();

/** @type {Map<string, string>} idempotencyKey → paymentId */
const _idempotencyIndex = new Map();

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const VALID_CURRENCIES = new Set(['USD', 'EUR', 'GBP', 'BRL']);
const VALID_STATUSES = new Set(['pending', 'confirmed', 'failed', 'cancelled']);

// ---------------------------------------------------------------------------
// PaymentProcessor
// ---------------------------------------------------------------------------

class PaymentProcessor {
  /**
   * Initiate a new payment.
   *
   * @param {{ loanId: string, payerId: string, amount: number, currency?: string, idempotencyKey?: string }} params
   * @returns {Object} The created (or existing idempotent) payment record.
   * @throws {Error} If required fields are missing or amount is not positive.
   */
  initiatePayment({ loanId, payerId, amount, currency = 'USD', idempotencyKey } = {}) {
    if (!loanId || typeof loanId !== 'string') {
      throw new Error('loanId is required');
    }
    if (!payerId || typeof payerId !== 'string') {
      throw new Error('payerId is required');
    }
    if (typeof amount !== 'number' || isNaN(amount)) {
      throw new Error('amount must be a number');
    }
    if (amount <= 0) {
      throw new Error('amount must be a positive number');
    }

    const normalizedCurrency = String(currency).trim().toUpperCase();
    if (!normalizedCurrency) {
      throw new Error('currency must be a non-empty string');
    }

    // Idempotency: return existing payment if key already used
    if (idempotencyKey && _idempotencyIndex.has(idempotencyKey)) {
      const existingId = _idempotencyIndex.get(idempotencyKey);
      if (_paymentStore.has(existingId)) {
        return _paymentStore.get(existingId);
      }
    }

    const paymentId = crypto.randomUUID();
    const payment = {
      paymentId,
      loanId,
      payerId,
      amount: Number(amount),
      currency: normalizedCurrency,
      status: 'pending',
      createdAt: new Date().toISOString(),
    };

    if (idempotencyKey) {
      payment.idempotencyKey = idempotencyKey;
      _idempotencyIndex.set(idempotencyKey, paymentId);
    }

    _paymentStore.set(paymentId, payment);
    return payment;
  }

  /**
   * Confirm a pending payment.
   *
   * @param {string} paymentId
   * @param {string} [transactionReference]
   * @returns {Object} The updated payment record.
   * @throws {Error} 'PAYMENT_NOT_FOUND' if paymentId does not exist.
   * @throws {Error} 'INVALID_STATUS_TRANSITION' if payment is not pending.
   */
  confirmPayment(paymentId, transactionReference) {
    if (!paymentId) {
      throw new Error('paymentId is required');
    }
    const payment = _paymentStore.get(paymentId);
    if (!payment) {
      throw new Error('PAYMENT_NOT_FOUND');
    }
    if (payment.status !== 'pending') {
      throw new Error(
        `INVALID_STATUS_TRANSITION: Cannot confirm payment in '${payment.status}' status. Only pending payments can be confirmed.`
      );
    }

    payment.status = 'confirmed';
    if (transactionReference) {
      payment.transactionReference = transactionReference;
    }
    payment.confirmedAt = new Date().toISOString();
    return payment;
  }

  /**
   * Cancel a pending payment.
   *
   * @param {string} paymentId
   * @returns {Object} The updated payment record.
   * @throws {Error} 'PAYMENT_NOT_FOUND' if paymentId does not exist.
   * @throws {Error} 'INVALID_STATUS_TRANSITION' if payment is not pending.
   */
  cancelPayment(paymentId) {
    if (!paymentId) {
      throw new Error('paymentId is required');
    }
    const payment = _paymentStore.get(paymentId);
    if (!payment) {
      throw new Error('PAYMENT_NOT_FOUND');
    }
    if (payment.status !== 'pending') {
      throw new Error(
        `INVALID_STATUS_TRANSITION: Cannot cancel payment in '${payment.status}' status.`
      );
    }

    payment.status = 'cancelled';
    payment.cancelledAt = new Date().toISOString();
    return payment;
  }

  /**
   * Retrieve a payment by ID.
   *
   * @param {string} paymentId
   * @returns {Object|null} The payment record or null if not found.
   */
  getPayment(paymentId) {
    return _paymentStore.get(paymentId) || null;
  }

  /**
   * Look up a payment by its idempotency key.
   *
   * @param {string} idempotencyKey
   * @returns {Object|null} The payment record or null.
   */
  getByIdempotencyKey(idempotencyKey) {
    const paymentId = _idempotencyIndex.get(idempotencyKey);
    if (!paymentId) return null;
    return _paymentStore.get(paymentId) || null;
  }

  /** Clear all internal state (used in tests). */
  _reset() {
    _paymentStore.clear();
    _idempotencyIndex.clear();
  }
}

module.exports = { PaymentProcessor, _paymentStore, _idempotencyIndex };
