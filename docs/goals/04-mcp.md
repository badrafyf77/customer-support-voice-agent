# Chapter 4: Connect the Tools with MCP

**MCP** (Model Context Protocol) is like a USB port for AI tools. We write our
tools once as an **MCP server**, and any AI app that speaks MCP can use them.

## What to do

- Put the shop tools (orders, tickets, refunds) in an MCP server.
- The voice agent connects to it.

## Use all three MCP parts

| Part | Who decides to use it | Example |
| --- | --- | --- |
| **Tools** | The AI | `create_ticket` |
| **Resources** | Our app | The customer's profile, loaded at the start of the call. |
| **Prompts** | A human | A ready-made instruction like `/summarize_call`. |

## The impressive demo

We connect the **same** MCP server to Claude Desktop too. Now a manager can type
"show me today's open tickets" in Claude Desktop.

One server, two different apps. This is exactly the main idea of Chapter 4.

## Safety

- Run the MCP server in a container (Docker).
- Protect it with a password (a token).
- Keep **two servers**: one that can only read data, and one that can change
  data. This way, an app that only needs to read can't change anything.

## Done when

- [ ] The shop tools run as an MCP server.
- [ ] The voice agent uses the tools through MCP.
- [ ] Tools, resources and prompts are all used.
- [ ] There is a read-only server and a server that can change data.
- [ ] The servers run in Docker with a token.
- [ ] The Claude Desktop demo works.
