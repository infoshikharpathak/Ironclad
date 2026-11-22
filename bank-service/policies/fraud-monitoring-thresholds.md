---
level: internal
---

# Fraud Monitoring Thresholds

Effective date: 2026-11-01

## Purpose

Internal only. These thresholds decide when Ironclad's fraud team reviews a customer's activity. They are not shown to customers, so that they cannot be worked around.

## OTP failure alerts

An account is flagged for review after 3 cancelled transfers caused by too many wrong OTP attempts within 24 hours, or 6 wrong OTP entries across any transfers within one hour.

## Transfer pattern alerts

A transfer to a person the customer has never paid before is flagged when it is above $2,500. Three or more transfers to new recipients within one hour are flagged regardless of amount. Transfers that use more than 80% of the daily person-to-person limit within 15 minutes of a password or device change are flagged as high risk.

## Memo and message alerts

Incoming payments whose memo contains instructions addressed to an assistant or AI, or a request to send money onward, are flagged and counted per sender. A sender with 2 or more flagged memos in 30 days is reported to the merchant and fraud teams.

## Review times

High-risk flags are reviewed within 30 minutes during support hours and within 2 hours outside them. Other flags are reviewed within one business day.
