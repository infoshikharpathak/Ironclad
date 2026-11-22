# AI Agents at Ironclad

Effective date: 2026-11-01

## What Ironclad's assistant can do

Ironclad's AI assistant can look up your accounts, balances and recent transactions, search the public directory to verify a recipient, answer questions from Ironclad's policies, and start a transfer on your behalf. It must look up your accounts and verify the recipient before it can start a transfer.

## Only you approve

Every transfer the assistant starts is a pending request that needs your one-time passcode, entered in the Ironclad app. The assistant never receives your OTP and cannot approve anything. If the assistant tells you a transfer is complete before you have approved it, something is wrong; report it.

## Governance

Every action the assistant takes goes through Ironclad's governance layer, which checks that the action is allowed, that required steps happened first, and that data passed to or from the assistant contains no hidden instructions. Actions that fail these checks are blocked and logged.

## Agents outside Ironclad

AI agents from other companies cannot start transfers from your Ironclad account. The only way an outside service can ask you for money is a merchant payment request from a registered merchant.

## Merchant AI agents

A merchant's own AI assistant can start a payment request only if the merchant has opted in to agent payments with Ironclad. These payments are labelled as started by the merchant's AI agent, are subject to the merchant's limit, and still need your OTP. Merchants that have not opted in, such as QuickMart, are refused when an AI agent starts a payment request.
