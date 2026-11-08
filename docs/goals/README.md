# Project Goals

This folder describes what we want to build, and why. It is the plan for the
final project of the **IA agentique** module (Master 2 AI Systems Engineering).

The goal: turn this voice app into an **English-only customer support voice
agent** that uses everything from the 5 course chapters.

## Files in this folder

| File | What it covers |
| --- | --- |
| [roadmap.md](./roadmap.md) | The order of the work, with checkboxes. |
| [01-foundations.md](./01-foundations.md) | Chapter 1: break the work into steps, and measure everything. |
| [02-reflection.md](./02-reflection.md) | Chapter 2: the agent checks its own work. |
| [03-tools.md](./03-tools.md) | Chapter 3: give the agent tools. |
| [04-mcp.md](./04-mcp.md) | Chapter 4: connect the tools with MCP. |
| [05-multi-agent.md](./05-multi-agent.md) | Chapter 5: a team of agents, and plans. |
| [presentation.md](./presentation.md) | What will impress at the final presentation. |

## Where the project is today

**What already works well:**
The app can hold a live voice conversation. It listens, turns speech into text,
sends the text to an AI model, and turns the answer back into speech, all fast.
It also handles the user interrupting. This is the hardest part to build, and
it already works.

**What is missing:**
Right now the AI only *talks*. It can't *do* anything:

- It can't look up an order.
- It can't check a database.
- It can't create a support ticket.
- It never checks its own answers.

Chapter 1 calls this "non-agentic": one question in, one answer out, no steps
in between. To make it agentic, the AI has to work in steps, use tools, and
check its work. The files in this folder explain how to get there.

## The fake company

The agent needs a business to support. We invent one, for example an online
shop called **"ShopEasy"**. It must be a made-up name, not a real company.

The shop gets a small database with:

- customers
- orders
- deliveries
- a return policy
- a short FAQ (common questions and answers)

This gives the agent real things to look up and act on.

## Rules we follow

- **English only.** The agent speaks and understands English.
- **Predictable before clever.** The course says companies prefer agents that
  behave the same way every time. We give the AI freedom only where it is safe.
- **Humans approve risky actions.** The agent never does something that can't
  be undone (like a refund) on its own.
- **Measure everything.** Every feature must be tested, with real numbers.
