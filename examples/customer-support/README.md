# Customer-support example

This fictional project demonstrates every check type without calling a model or connecting to a service.

From the repository root:

```shell
copilot-agent-contracts check \
  --config examples/customer-support/agent-contracts.toml \
  --verbose
```

The routing cases include an intentional overlap: a customer reports a product error and asks for money back. The longer billing phrase wins the routing check, while the documented mode order makes `Refund` outrank `Troubleshoot`.
