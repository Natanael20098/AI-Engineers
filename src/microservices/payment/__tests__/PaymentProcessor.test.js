'use strict';
/**
 * Unit tests for PaymentProcessor.js
 *
 * Acceptance criteria:
 *  - All unit tests pass success criteria on local and CI/CD environment.
 *  - Critical functions in PaymentProcessor.js achieve over 90% test coverage.
 *  - Each critical function has at least one success and one failure case.
 *
 * Critical functions under test:
 *  - initiatePayment()
 *  - confirmPayment()
 *  - cancelPayment()
 *  - getPayment()
 *  - getByIdempotencyKey()
 */

const { PaymentProcessor } = require('../PaymentProcessor');

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

let proc;

beforeEach(() => {
  proc = new PaymentProcessor();
  proc._reset();
});

afterEach(() => {
  proc._reset();
});

function makePayment(overrides = {}) {
  return proc.initiatePayment({
    loanId: 'loan-001',
    payerId: 'payer-001',
    amount: 500.0,
    currency: 'USD',
    ...overrides,
  });
}

// ---------------------------------------------------------------------------
// initiatePayment()
// ---------------------------------------------------------------------------

describe('initiatePayment()', () => {
  test('SUCCESS – returns a payment record in pending status', () => {
    const payment = makePayment();

    expect(payment.paymentId).toBeDefined();
    expect(payment.loanId).toBe('loan-001');
    expect(payment.payerId).toBe('payer-001');
    expect(payment.amount).toBe(500.0);
    expect(payment.currency).toBe('USD');
    expect(payment.status).toBe('pending');
    expect(payment.createdAt).toBeDefined();
  });

  test('SUCCESS – normalises currency to uppercase', () => {
    const payment = makePayment({ currency: 'eur' });
    expect(payment.currency).toBe('EUR');
  });

  test('SUCCESS – trims whitespace from currency', () => {
    const payment = makePayment({ currency: '  gbp  ' });
    expect(payment.currency).toBe('GBP');
  });

  test('SUCCESS – each payment receives a unique ID', () => {
    const ids = new Set([
      makePayment().paymentId,
      makePayment().paymentId,
      makePayment().paymentId,
    ]);
    expect(ids.size).toBe(3);
  });

  test('SUCCESS – idempotency key returns existing payment on duplicate call', () => {
    const p1 = makePayment({ idempotencyKey: 'idem-key-001' });
    const p2 = makePayment({ idempotencyKey: 'idem-key-001' });

    expect(p1.paymentId).toBe(p2.paymentId);
  });

  test('SUCCESS – different idempotency keys create different payments', () => {
    const p1 = makePayment({ idempotencyKey: 'key-A' });
    const p2 = makePayment({ idempotencyKey: 'key-B' });

    expect(p1.paymentId).not.toBe(p2.paymentId);
  });

  test('SUCCESS – idempotency key is stored on the payment record', () => {
    const payment = makePayment({ idempotencyKey: 'my-key' });
    expect(payment.idempotencyKey).toBe('my-key');
  });

  test('FAILURE – throws if loanId is missing', () => {
    expect(() =>
      proc.initiatePayment({ payerId: 'p1', amount: 100 })
    ).toThrow('loanId is required');
  });

  test('FAILURE – throws if payerId is missing', () => {
    expect(() =>
      proc.initiatePayment({ loanId: 'l1', amount: 100 })
    ).toThrow('payerId is required');
  });

  test('FAILURE – throws if amount is missing', () => {
    expect(() =>
      proc.initiatePayment({ loanId: 'l1', payerId: 'p1' })
    ).toThrow('amount must be a number');
  });

  test('FAILURE – throws if amount is zero', () => {
    expect(() =>
      proc.initiatePayment({ loanId: 'l1', payerId: 'p1', amount: 0 })
    ).toThrow('amount must be a positive number');
  });

  test('FAILURE – throws if amount is negative', () => {
    expect(() =>
      proc.initiatePayment({ loanId: 'l1', payerId: 'p1', amount: -100 })
    ).toThrow('amount must be a positive number');
  });

  test('FAILURE – throws if amount is NaN', () => {
    expect(() =>
      proc.initiatePayment({ loanId: 'l1', payerId: 'p1', amount: NaN })
    ).toThrow('amount must be a number');
  });

  test('FAILURE – throws if called with no arguments', () => {
    expect(() => proc.initiatePayment()).toThrow();
  });
});

// ---------------------------------------------------------------------------
// confirmPayment()
// ---------------------------------------------------------------------------

describe('confirmPayment()', () => {
  test('SUCCESS – confirms a pending payment', () => {
    const { paymentId } = makePayment();
    const confirmed = proc.confirmPayment(paymentId);

    expect(confirmed.status).toBe('confirmed');
    expect(confirmed.confirmedAt).toBeDefined();
  });

  test('SUCCESS – stores transaction reference when provided', () => {
    const { paymentId } = makePayment();
    const confirmed = proc.confirmPayment(paymentId, 'TXN-REF-001');

    expect(confirmed.transactionReference).toBe('TXN-REF-001');
  });

  test('SUCCESS – confirmation without transaction reference is valid', () => {
    const { paymentId } = makePayment();
    const confirmed = proc.confirmPayment(paymentId);

    expect(confirmed.status).toBe('confirmed');
    expect(confirmed.transactionReference).toBeUndefined();
  });

  test('FAILURE – throws PAYMENT_NOT_FOUND for unknown paymentId', () => {
    expect(() => proc.confirmPayment('non-existent-id')).toThrow('PAYMENT_NOT_FOUND');
  });

  test('FAILURE – throws INVALID_STATUS_TRANSITION when confirming already-confirmed payment', () => {
    const { paymentId } = makePayment();
    proc.confirmPayment(paymentId);

    expect(() => proc.confirmPayment(paymentId)).toThrow('INVALID_STATUS_TRANSITION');
  });

  test('FAILURE – throws INVALID_STATUS_TRANSITION when confirming a cancelled payment', () => {
    const { paymentId } = makePayment();
    proc.cancelPayment(paymentId);

    expect(() => proc.confirmPayment(paymentId)).toThrow('INVALID_STATUS_TRANSITION');
  });

  test('FAILURE – throws if paymentId is falsy', () => {
    expect(() => proc.confirmPayment(null)).toThrow('paymentId is required');
    expect(() => proc.confirmPayment('')).toThrow('paymentId is required');
  });
});

// ---------------------------------------------------------------------------
// cancelPayment()
// ---------------------------------------------------------------------------

describe('cancelPayment()', () => {
  test('SUCCESS – cancels a pending payment', () => {
    const { paymentId } = makePayment();
    const cancelled = proc.cancelPayment(paymentId);

    expect(cancelled.status).toBe('cancelled');
    expect(cancelled.cancelledAt).toBeDefined();
  });

  test('FAILURE – throws PAYMENT_NOT_FOUND for unknown paymentId', () => {
    expect(() => proc.cancelPayment('no-such-id')).toThrow('PAYMENT_NOT_FOUND');
  });

  test('FAILURE – throws INVALID_STATUS_TRANSITION when cancelling an already-cancelled payment', () => {
    const { paymentId } = makePayment();
    proc.cancelPayment(paymentId);

    expect(() => proc.cancelPayment(paymentId)).toThrow('INVALID_STATUS_TRANSITION');
  });

  test('FAILURE – throws INVALID_STATUS_TRANSITION when cancelling a confirmed payment', () => {
    const { paymentId } = makePayment();
    proc.confirmPayment(paymentId);

    expect(() => proc.cancelPayment(paymentId)).toThrow('INVALID_STATUS_TRANSITION');
  });

  test('FAILURE – throws if paymentId is falsy', () => {
    expect(() => proc.cancelPayment(undefined)).toThrow('paymentId is required');
  });
});

// ---------------------------------------------------------------------------
// getPayment()
// ---------------------------------------------------------------------------

describe('getPayment()', () => {
  test('SUCCESS – returns payment record for existing paymentId', () => {
    const { paymentId } = makePayment();
    const retrieved = proc.getPayment(paymentId);

    expect(retrieved).not.toBeNull();
    expect(retrieved.paymentId).toBe(paymentId);
    expect(retrieved.status).toBe('pending');
  });

  test('SUCCESS – reflects confirmed status after confirmation', () => {
    const { paymentId } = makePayment();
    proc.confirmPayment(paymentId);

    const retrieved = proc.getPayment(paymentId);
    expect(retrieved.status).toBe('confirmed');
  });

  test('FAILURE – returns null for unknown paymentId', () => {
    expect(proc.getPayment('no-such-id')).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// getByIdempotencyKey()
// ---------------------------------------------------------------------------

describe('getByIdempotencyKey()', () => {
  test('SUCCESS – retrieves payment by its idempotency key', () => {
    const payment = makePayment({ idempotencyKey: 'unique-key' });
    const retrieved = proc.getByIdempotencyKey('unique-key');

    expect(retrieved).not.toBeNull();
    expect(retrieved.paymentId).toBe(payment.paymentId);
  });

  test('FAILURE – returns null for unknown idempotency key', () => {
    expect(proc.getByIdempotencyKey('unknown-key')).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Full payment lifecycle
// ---------------------------------------------------------------------------

describe('Full payment lifecycle', () => {
  test('initiate → confirm is a valid flow', () => {
    const { paymentId } = makePayment();
    expect(proc.getPayment(paymentId).status).toBe('pending');

    proc.confirmPayment(paymentId, 'TXN-999');
    expect(proc.getPayment(paymentId).status).toBe('confirmed');
    expect(proc.getPayment(paymentId).transactionReference).toBe('TXN-999');
  });

  test('initiate → cancel is a valid flow', () => {
    const { paymentId } = makePayment();
    proc.cancelPayment(paymentId);
    expect(proc.getPayment(paymentId).status).toBe('cancelled');
  });

  test('data integrity: amount and currency are preserved through state changes', () => {
    const payment = makePayment({ amount: 1250.99, currency: 'EUR' });
    proc.confirmPayment(payment.paymentId);
    const retrieved = proc.getPayment(payment.paymentId);

    expect(retrieved.amount).toBe(1250.99);
    expect(retrieved.currency).toBe('EUR');
  });
});
