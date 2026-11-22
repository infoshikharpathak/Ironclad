# Answer quality: 10 held-out questions through the banking agent

Each question in a new agent session (gpt-4o-mini, Ironclad's banking agent with the internal policy key), with the bank's search in vector-only mode (the previous retrieval: child chunks, cosine >= 0.43) and in hybrid + parent-child mode. Judged by hand against the policy text: is the answer correct, does it cite the section the answer comes from, does it state anything the policies don't say.

| Setup | Correct | Cites the right section | Partly right citation | Invents anything |
|---|---|---|---|---|
| vector only | 9/10 | 5/8 | 2/8 | 0/10 |
| hybrid + parent-child | 9/10 | 5/8 | 2/8 | 0/10 |

(8 questions need a citation: h01 was answered wrongly and h16 isn't covered.)

| Setup | Id | Question | Session | Correct | Citation | Invents | Note |
|---|---|---|---|---|---|---|---|
| vector | h01 | Is there a foreign transaction fee? | `answers-vector-h01-f74c` | no | — | no | Same as hybrid. |
| vector | h02 | How often is savings interest paid? | `answers-vector-h02-d40e` | yes | yes | no |  |
| vector | h03 | What is QuickMart's maximum payment amount? | `answers-vector-h03-60bf` | yes | yes | no |  |
| vector | h05 | Is phone support available around the clock? | `answers-vector-h05-d129` | yes | yes | no |  |
| vector | h07 | What happens if I mistype the six digits three times? | `answers-vector-h07-61ed` | yes | partial | no | Same internal threshold, same mis-citation. |
| vector | h08 | Who actually gets my money when I buy food through the app? | `answers-vector-h08-17a5` | yes | partial | no | The payee fact comes from Who receives the money, but only How merchant payments work is cited. |
| vector | h10 | Will you warn me before the savings rate goes down? | `answers-vector-h10-e5ab` | yes | yes | no |  |
| vector | h12 | Can some random shopping bot pull money out of my account? | `answers-vector-h12-4048` | yes | no | no | Cites Reporting fraud. |
| vector | h14 | Can I move $20,000 from savings to checking, and does savings pay interest? | `answers-vector-h14-fc12` | yes | yes | no | Cites both sections (it searched twice). |
| vector | h16 | Can I get a personal loan? | `answers-vector-h16-cb19` | yes | — | no | Not covered, suggests support. |
| hybrid | h01 | Is there a foreign transaction fee? | `answers-hybrid-h01-56c5` | no | — | no | Search returned nothing; said not covered, but Other fees says there are none. |
| hybrid | h02 | How often is savings interest paid? | `answers-hybrid-h02-7c88` | yes | yes | no |  |
| hybrid | h03 | What is QuickMart's maximum payment amount? | `answers-hybrid-h03-3e9e` | yes | yes | no |  |
| hybrid | h05 | Is phone support available around the clock? | `answers-hybrid-h05-919c` | yes | yes | no |  |
| hybrid | h07 | What happens if I mistype the six digits three times? | `answers-hybrid-h07-b10e` | yes | partial | no | Adds an internal fraud threshold (from fraud-monitoring-thresholds) and cites it to the public Wrong codes section. |
| hybrid | h08 | Who actually gets my money when I buy food through the app? | `answers-hybrid-h08-2f4f` | yes | yes | no | Cites both How merchant payments work and Who receives the money. |
| hybrid | h10 | Will you warn me before the savings rate goes down? | `answers-hybrid-h10-b3af` | yes | yes | no |  |
| hybrid | h12 | Can some random shopping bot pull money out of my account? | `answers-hybrid-h12-8db7` | yes | no | no | Right answer, but cites Reporting fraud; the AI agents sections weren't used. |
| hybrid | h14 | Can I move $20,000 from savings to checking, and does savings pay interest? | `answers-hybrid-h14-7295` | yes | partial | no | Cites the interest section; the own-accounts transfer rule isn't cited (answered from the balance). |
| hybrid | h16 | Can I get a personal loan? | `answers-hybrid-h16-d980` | yes | — | no | Not covered, suggests support. |

## Replies

**vector h01**: Is there a foreign transaction fee?

> The policy documents do not mention a foreign transaction fee. For more specific inquiries or details, I recommend contacting Customer Support.

**vector h02**: How often is savings interest paid?

> Savings interest is calculated daily on the end-of-day balance in your savings account and is paid into the savings account on the first business day of each month (Savings Interest, How interest is calculated).

**vector h03**: What is QuickMart's maximum payment amount?

> QuickMart's maximum payment amount is $500.00 per payment request (Merchant Payments, Merchant limits). If you attempt to make a request above this limit, it will be refused before it reaches you.

**vector h05**: Is phone support available around the clock?

> Phone support is available 24 hours a day, 7 days a week, but only for reporting fraud or a lost device. For general inquiries, customer support is available through chat in the Ironclad app from 8:00 AM to 8:00 PM Eastern Time, Monday to Saturday (Customer Support, Hours).

**vector h07**: What happens if I mistype the six digits three times?

> If you mistype the six-digit OTP three times, your request will be canceled for your protection, and you'll need to start a new request. Additionally, if you have three canceled transfers due to incorrect OTP attempts within 24 hours, your account may be flagged for review (OTP and Transfer Security, Wrong codes).

**vector h08**: Who actually gets my money when I buy food through the app?

> When you buy food through the app, your money goes to the registered merchant, such as FoodDash. Here's how it works:
> 
> 1. The merchant sends Ironclad a payment request with the amount.
> 2. Ironclad creates a pending payment from your checking account to the merchant's settlement account.
> 3. The payment only goes through after you approve the transaction with your OTP.
> 
> In summary, the payment is directed to the merchant's own settlement account as recorded in Ironclad's merchant registry, and they cannot choose a different payee (Merchant Payments, How Merchant Payments Work).

**vector h10**: Will you warn me before the savings rate goes down?

> Ironclad will provide at least 30 days' notice in the app before lowering the savings rate (Savings Interest, Rate changes). Make sure to keep an eye on the app for any notifications about changes to your savings interest rate!

**vector h12**: Can some random shopping bot pull money out of my account?

> No, a random shopping bot cannot pull money from your account without your approval. You are only responsible for transactions that you authorize using your one-time passcode (OTP). If someone accesses your account without permission and initiates a transfer, you are not liable for it.
> 
> If you notice any suspicious activity, such as unexpected transfer requests or communications asking for your OTP, it's crucial to decline any unauthorized transactions and contact Customer Support immediately (Fraud and Account Freezes, Reporting Fraud). 
> 
> If you have further concerns or issues, please let me know!

**vector h14**: Can I move $20,000 from savings to checking, and does savings pay interest?

> You currently have the following account balances:
> - **Checking:** $10,000
> - **Savings:** $5,000
> 
> 1. **Interest on Savings:** Yes, your savings account earns interest. It has a variable rate of 2.10% annual percentage yield (APY). Interest is calculated daily and paid into your savings account on the first business day of each month (Savings Interest, How interest is calculated).
> 
> 2. **Moving $20,000 from Savings to Checking:** You cannot move $20,000 because your current savings balance is only $5,000. However, there are no per-transfer or daily caps on moving money between your own accounts, as long as you have sufficient funds in the account you are sending from (Transfer Limits, Transfers between your own accounts). 
> 
> If you want to transfer any other amount or have further questions, feel free to ask!

**vector h16**: Can I get a personal loan?

> It seems that Ironclad's policies do not cover personal loans. I recommend contacting Customer Support for more information on loan options available to you.

**hybrid h01**: Is there a foreign transaction fee?

> The policy documents do not provide information on foreign transaction fees. I recommend contacting Customer Support for detailed inquiries related to this topic.

**hybrid h02**: How often is savings interest paid?

> Savings interest is calculated daily on the end-of-day balance in your savings account and is paid into the savings account on the first business day of each month (Savings Interest, How interest is calculated).

**hybrid h03**: What is QuickMart's maximum payment amount?

> QuickMart's maximum payment request amount is **$500.00**. Any payment request exceeding this limit will be refused before it reaches you (Merchant Payments, Merchant Limits).

**hybrid h05**: Is phone support available around the clock?

> Phone support is available 24 hours a day, 7 days a week, but only for reporting fraud or a lost device. For other inquiries, customer support via chat is available from 8:00 AM to 8:00 PM Eastern Time, Monday to Saturday (Customer Support, Hours).

**hybrid h07**: What happens if I mistype the six digits three times?

> If you mistype the six-digit OTP three times, the request is canceled for your protection, and you'll need to start a new request. Additionally, if there are three canceled transfers due to wrong OTP attempts within 24 hours, your account might be flagged for review (OTP and Transfer Security, Wrong codes).

**hybrid h08**: Who actually gets my money when I buy food through the app?

> When you buy food through the app, your payment goes directly to the merchant's own settlement account, which is recorded in Ironclad's merchant registry. For example, if you order from a registered merchant like FoodDash, they send Ironclad a payment request for the order amount. Ironclad creates a pending payment from your account to the merchant's account, and the money is only transferred after you approve the payment with your OTP (Merchant Payments, How merchant payments work and Who receives the money).

**hybrid h10**: Will you warn me before the savings rate goes down?

> Yes, you will be warned before the savings rate goes down. Ironclad gives at least 30 days' notice in the app before lowering the rate (Savings Interest, Rate changes).

**hybrid h12**: Can some random shopping bot pull money out of my account?

> No, a random shopping bot cannot pull money out of your account. Ironclad's AI assistant can only read your accounts and transactions to respond to your requests, and it does not receive one-time passcodes (OTPs) required for transactions.
> 
> If you suspect someone has accessed your account, decline any unrecognized pending transfers and contact Customer Support immediately. You are not responsible for any transfers made without your OTP approval (Fraud and Account Freezes, Reporting fraud). 
> 
> If you have any more questions or need assistance, feel free to ask!

**hybrid h14**: Can I move $20,000 from savings to checking, and does savings pay interest?

> You cannot move $20,000 from savings to checking because your savings balance is only $5,000. You do, however, have $10,000 in your checking account.
> 
> Regarding savings, yes, Ironclad Savings does earn interest at a variable rate of 2.10% annual percentage yield (APY). Interest is calculated daily on the end-of-day balance and paid into the savings account on the first business day of each month (Savings Interest, How interest is calculated). 
> 
> If you need assistance with something else or wish to move a different amount, let me know!

**hybrid h16**: Can I get a personal loan?

> It seems that the policy documents do not provide information about personal loans. I recommend contacting Customer Support for assistance regarding loan options available at Ironclad Bank.

