# Merchant Payments

Effective date: 2026-11-01

## How merchant payments work

Registered merchants, such as FoodDash, can ask you to pay for an order through Ironclad. The merchant sends Ironclad a payment request with the amount and its order reference. Ironclad creates a pending payment from your checking account to the merchant's settlement account and shows it in your app as "Pay $X to {merchant} (merchant)". The money moves only after you approve the payment with your OTP.

## Who receives the money

A payment always goes to the merchant's own settlement account recorded in Ironclad's merchant registry. A merchant cannot choose a different payee or ask Ironclad to send your money to any other account.

## Merchant limits

Each merchant has a maximum amount per payment request. FoodDash payment requests are limited to $200.00. QuickMart payment requests are limited to $500.00. A request above the merchant's limit is refused before it reaches you.

## Payments started by a merchant's AI agent

A merchant's AI assistant may start a payment request only if the merchant has opted in to agent payments with Ironclad. FoodDash has opted in. QuickMart has not, so QuickMart payment requests started by an AI agent are refused. Payments started by an agent are labelled "Started by {merchant}'s AI agent" and still need your OTP.

## Expiry and cancellation

A payment request expires 5 minutes after it is created if you have not approved it. A merchant may withdraw a pending payment request at any time before you approve it, for example when you cancel the order; the request then closes and your app stops showing it. Once you have approved a payment it cannot be cancelled by the merchant.

## Refunds

Ironclad does not reverse approved merchant payments automatically. If you cancel an order after paying, ask the merchant for a refund; see the Disputes and Refunds policy if the merchant does not resolve it.
