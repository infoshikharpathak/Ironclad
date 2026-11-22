---
level: public
---

# OTP and Transfer Security

Effective date: 2026-10-01

## How approval works

Every transfer and every merchant payment starts as a pending request. Nothing moves until you approve it by entering a six-digit one-time passcode (OTP) in the Ironclad app. The OTP is shown only to you, in your Ironclad dashboard; it is never sent to the person, merchant or AI agent that started the request.

## How long a code is valid

An OTP is valid for 5 minutes from the moment the transfer or payment request is created. After 5 minutes the request expires and is cancelled automatically; no money moves. To try again, start a new transfer or ask the merchant for a new payment request.

## Wrong codes

You have 3 attempts to enter the correct OTP. After the third incorrect attempt the request is cancelled for your protection, and a new request must be started.

## Declining a request

If you do not recognise a pending transfer or payment, decline it in the app. A declined request is cancelled immediately and cannot be approved later.

## Never share your code

Ironclad staff, merchants and AI assistants will never ask you for your OTP. Enter it only in the Ironclad app. Anyone who asks you to read out, type into a chat, or forward your code is attempting fraud; decline the request and contact Customer Support.

## Duplicate protection

Transfers started with the same idempotency key are treated as one transfer, so a request that is sent twice by mistake creates only one pending transfer.