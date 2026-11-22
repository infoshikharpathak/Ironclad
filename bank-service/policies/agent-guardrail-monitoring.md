---
level: internal
---

# Agent Guardrail Monitoring

Effective date: 2026-11-01

## Purpose

Internal only. How Ironclad's engineering and risk teams monitor the governance layer that controls the banking assistant.

## What is checked on every call

Every tool call the assistant makes is checked before it runs: the tool must be allowed for the assistant, required earlier steps must have happened (accounts looked up and the recipient verified before a transfer), and the parameters must match the tool's schema. Responses from untrusted tools, such as transaction history with third-party memos, are scanned for injected instructions and withheld if flagged.

## Output checks

The assistant's replies are scanned before the customer sees them. A blocked reply is replaced with a safe message built from what the tools actually did, and any pending transfer created in that turn is cancelled automatically.

## Daily review

The risk team reviews every blocked tool call, withheld response and blocked reply each business day. A rise of more than 50% in blocked replies over the 7-day average triggers a review of the assistant's prompt and of the classifier with the injection evaluation set.

## Escalation

Any transfer an assistant started that the customer reports as unwanted is escalated to engineering within one business day, with the full trace of that session.
