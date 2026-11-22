---
level: internal
---

# Merchant Risk Rules

Effective date: 2026-11-01

## Purpose

Internal only. How Ironclad sets and reviews merchant limits and agent-payment permissions.

## Setting a merchant's limit

New merchants start with a maximum payment request of $200. A merchant may move to $500 after 90 days with a dispute rate below 0.5% of payments, and to $1,000 after a further 180 days at the same rate.

## Agent payments opt-in

A merchant may request AI agent payments only after 60 days of normal checkout payments with no confirmed fraud. Approval needs a review of the merchant's agent, including how it shows prices to customers and that it never asks customers for OTPs.

## Suspension triggers

A merchant is suspended when its dispute rate over 30 days exceeds 2%, when a merchant key is used from an unexpected network, or when its AI agent is found asking customers for OTPs. The merchant team cancels a suspended merchant's pending payment requests; new requests are refused automatically.

## Settlement holds

Settlement account balances above $50,000 are held for 2 business days before payout while disputes can still be opened.
