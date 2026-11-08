# Chapter 2: The Agent Checks Its Own Work (Reflection)

"Reflection" means the AI writes an answer, then reviews it, then fixes it.

## The problem with voice

In a voice call, the customer is waiting. We can't review every sentence,
because it would be too slow. So we only use reflection where it matters.

## Where we use reflection

### 1. Before a refund

A second AI checks the refund against:

- the **real order** in the database
- the **return policy**

Checking against real data is much stronger than the AI just rereading its own
text. The course calls this **external feedback**.

### 2. Before speaking

Fast code checks run on every answer before it is spoken:

- no competitor names
- the answer is not too long
- no lists or symbols that sound strange when spoken

If a check fails, the AI rewrites the answer. These checks are plain code, so
they cost nothing and are instant.

### 3. After the call

1. The AI writes a call summary.
2. A second AI reviews it.
3. The first AI fixes it.

This runs after the call ends, so the customer never waits for it.

## Keep it limited

Each review loop runs **at most 1 or 2 times**. Without a limit, the reviewer
can keep finding small things to change forever.

## Prove that it helps

We run the same test calls **with** and **without** reflection, then show the
scores side by side. For example: "87% correct without, 95% with".

## Done when

- [ ] Refunds are checked against the real order and the policy.
- [ ] The speaking checks run before every answer.
- [ ] The after-call summary is reviewed and fixed.
- [ ] We have a table of scores with and without reflection.
