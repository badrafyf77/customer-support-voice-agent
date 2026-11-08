# Chapter 1: Break the Work into Steps, and Measure Everything

## Split a support call into small steps

A human support worker follows steps, and our agent should too:

1. Find out who the customer is.
2. Check their identity.
3. Understand the problem.
4. Look up the data.
5. Check the company rules.
6. Do the action.
7. Confirm with the customer.
8. Write a summary.

For each step, we decide who does it: **the AI**, **plain code**, or **a human**.

## Don't give the AI too much freedom

The course says companies prefer agents that are predictable. So:

- **Steps 1 and 2 are fixed in code.** The AI can't skip them.
- **In the middle of the call**, the AI chooses from a fixed list of tools.

The course calls this "semi-autonomous". We explain this choice in the report.

## A human approves risky actions

Some actions can't be undone, like a refund. The agent must **never** do these
alone. Instead:

1. The agent puts the request in a waiting list.
2. A human opens a web page and clicks **Approve** or **Reject**.
3. Only an approved request is carried out.

The course calls this **human-in-the-loop**. Each request in the list has one of
three states: waiting, approved, rejected.

## Record every step (traces)

We save one log line for each step:

- the time
- the step name
- what went in
- what came out
- which model or tool was used
- how long it took

When something goes wrong, the log shows where.

## Test the agent automatically (evals)

There are two kinds of test:

- **Code tests:** simple checks written in Python. Does the answer mention a
  competitor? Does it say the order number?
- **AI-judge tests:** a second AI grades the answer with yes/no questions. Did
  it answer the question? Was it polite? The course says yes/no questions work
  better than scores out of 5.

We test the whole call **and** each step on its own, so we know which step to
fix.

## Use two models

- A **small, fast model** talks to the customer.
- A **bigger, smarter model** handles hard thinking, like planning or checking.

## Done when

- [ ] The 8 steps are written down, and each one says who does it.
- [ ] Steps 1 and 2 are fixed in code.
- [ ] The human approval list works.
- [ ] Every step writes a log line.
- [ ] Code tests and AI-judge tests run automatically.
