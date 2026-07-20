---
name: Request Refund
description: Collect the facts needed to evaluate a customer refund request.
agent: agent
---

Collect the order date, product, reason, and purchase channel. Evaluate the request against the documented policy. Do not decide eligibility from the prompt alone.

## Examples

```json
{
  "orderDate": "2026-07-01",
  "reason": "Product does not start",
  "decision": "pending-policy-check"
}
```
