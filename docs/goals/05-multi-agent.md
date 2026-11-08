# Chapter 5: A Team of Agents, and Plans

## A team instead of one agent

One agent doing everything gets confused. We build a small team:

- A **main agent** that talks to the customer.
- **Helper agents** that each do one job:
  - **Orders agent:** deliveries and order questions
  - **Refunds agent:** returns and money
  - **FAQ agent:** general questions

The main agent is the boss and sends work to the helpers. The course calls this
the **supervisor** setup and says it's the best choice for companies. Each
helper only sees its own tools, so it makes fewer mistakes.

## Plans for complicated requests

Example: "Return the gold glasses I bought and refund my card."

1. The AI first writes a step-by-step plan in a strict format (JSON).
2. Our code checks that the plan is valid (for example, that every tool in it
   really exists).
3. The plan runs one step at a time.
4. Before any risky step, the agent asks the customer "Are you sure?".
5. Big refunds also need a human's approval.

## An analytics agent for the manager

The manager asks: "What was the most common problem this week?"

The AI writes a short Python script that reads the call data and finds the
answer. The script runs safely in a container. This is **Code as Action** from
Chapter 5: one small script instead of dozens of tool calls.

## An after-call checker

After each call, an agent grades it with the yes/no questions from
[01-foundations.md](./01-foundations.md). It doesn't slow down the call, because
it runs after the call ends.

## Done when

- [ ] The main agent sends work to the Orders, Refunds and FAQ helpers.
- [ ] Complicated requests use a JSON plan that code checks first.
- [ ] Risky steps ask "Are you sure?".
- [ ] The analytics agent answers manager questions with Python in Docker.
- [ ] Every call gets graded after it ends.
