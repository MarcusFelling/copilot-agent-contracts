# Customer-support example

This fictional project demonstrates every check type without calling a model or connecting to a service. The routing and precedence checks are the point; the frontmatter, sections, contains, and forbid checks hold the file to a shape around them.

From the repository root:

```shell
copilot-agent-contracts check \
  --config examples/customer-support/agent-contracts.toml \
  --verbose
```

The routing cases include an intentional overlap: a customer reports a product error and asks for money back. The longer billing phrase wins the routing check, while the documented mode order makes `Refund` outrank `Troubleshoot`.
