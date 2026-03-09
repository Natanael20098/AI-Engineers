'use strict';
/**
 * app.js – Express HTTP wrapper for PaymentProcessor.
 *
 * Exposes PaymentProcessor as a RESTful API for integration testing.
 *
 * Endpoints
 * ---------
 * GET  /health                              liveness probe
 * POST /payments/initiate                   initiate a new payment
 * GET  /payments/:paymentId                 retrieve payment status
 * POST /payments/:paymentId/confirm         confirm a pending payment
 * POST /payments/:paymentId/cancel          cancel a pending payment
 */

const express = require('express');
const { PaymentProcessor } = require('./PaymentProcessor');

function createPaymentApp(processor) {
  const proc = processor || new PaymentProcessor();
  const app = express();
  app.use(express.json());

  // -------------------------------------------------------------------------
  // Routes
  // -------------------------------------------------------------------------

  app.get('/health', (_req, res) => {
    res.json({ status: 'ok', service: 'payment_processor' });
  });

  app.post('/payments/initiate', (req, res) => {
    const { loanId, payerId, amount, currency, idempotencyKey } = req.body || {};
    if (!loanId || !payerId || amount === undefined) {
      return res.status(400).json({ error: 'loanId, payerId and amount are required' });
    }
    try {
      const payment = proc.initiatePayment({ loanId, payerId, amount, currency, idempotencyKey });
      return res.status(201).json(payment);
    } catch (err) {
      return res.status(400).json({ error: err.message });
    }
  });

  app.get('/payments/:paymentId', (req, res) => {
    const payment = proc.getPayment(req.params.paymentId);
    if (!payment) {
      return res.status(404).json({ error: `Payment '${req.params.paymentId}' not found` });
    }
    return res.status(200).json(payment);
  });

  app.post('/payments/:paymentId/confirm', (req, res) => {
    const { transactionReference } = req.body || {};
    try {
      const payment = proc.confirmPayment(req.params.paymentId, transactionReference);
      return res.status(200).json(payment);
    } catch (err) {
      if (err.message === 'PAYMENT_NOT_FOUND') {
        return res.status(404).json({ error: err.message });
      }
      return res.status(409).json({ error: err.message });
    }
  });

  app.post('/payments/:paymentId/cancel', (req, res) => {
    try {
      const payment = proc.cancelPayment(req.params.paymentId);
      return res.status(200).json(payment);
    } catch (err) {
      if (err.message === 'PAYMENT_NOT_FOUND') {
        return res.status(404).json({ error: err.message });
      }
      return res.status(409).json({ error: err.message });
    }
  });

  return app;
}

module.exports = { createPaymentApp };

if (require.main === module) {
  const app = createPaymentApp();
  const PORT = process.env.PORT || 3002;
  app.listen(PORT, () => {
    console.log(`Payment service listening on port ${PORT}`);
  });
}
