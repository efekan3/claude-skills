---
name: agentmail
description: "Use when an agent needs AgentMail CLI email inboxes."
---

<!-- claude-compat -->
> **Running this in Claude.** This skill was written for Hermes Agent. Read its tool names as:
> `terminal` → Bash · `read_file` → Read · `write_file` → Write · `patch` → Edit ·
> `search_files` → Grep / Glob · `web_search` → WebSearch · `web_extract` → WebFetch (or `curl`) ·
> `browser_*` → a browser tool or Playwright, if available · `vision_analyze` → open the image with Read ·
> `delegate_task` → the Agent tool (subagents) · `execute_code` → write a script and run it with Bash ·
> `clarify` → ask the user · `cronjob` → no built-in scheduler here: run the steps now, or offer to set up a scheduled task.
> `<skill-dir>` is this skill's folder (the base directory shown when the skill loads).
> `~/.hermes` / `HERMES_HOME` is only a folder for settings and caches; `hermes …` commands don't exist here — skip them.

# AgentMail Skill

AgentMail gives an agent its own email inbox for sending mail, receiving
replies, completing email OTP flows, and running inbound email loops. Use it for
agent-owned inboxes, not a user's existing IMAP/SMTP mailbox.

Use the `agentmail` CLI first. Use MCP only when the harness expects MCP tools;
use REST only when the CLI is missing a required operation.

## When to Use

- The agent needs an email address it owns.
- The task involves email OTP flows, replies, threads, labels, or attachments.
- The agent needs webhook or WebSocket delivery for inbound mail.

## Prerequisites

- Run commands through the `terminal` tool.
- Install the CLI:

```bash
npm install -g agentmail-cli@latest
```

- Export an API key:

```bash
export AGENTMAIL_API_KEY="am_..."
```

No API key yet? Use [signup.md](references/signup.md).

## How to Run

Use `--format json` whenever another command or script needs IDs.

```bash
agentmail inboxes list --format json
```

## Quick Reference

- [AgentMail agent reference](https://agentmail.md): hosted copy.
- [AgentMail](https://agentmail.to): product landing page.
- [Console](https://console.agentmail.to): API keys and account management.
- [Docs](https://docs.agentmail.to): full product documentation.
- [signup.md](references/signup.md): self-signup and OTP verification.
- [core.md](references/core.md): inboxes, messages, threads, labels, attachments.
- [webhooks.md](references/webhooks.md): events to a public HTTPS server.
- [websockets.md](references/websockets.md): events to a local agent process.
- [mcp.md](references/mcp.md): MCP integration.

## Procedure

1. Install `agentmail-cli@latest` and verify `agentmail inboxes list --format json`.
2. If no API key is available, complete [signup.md](references/signup.md).
3. Use [core.md](references/core.md) for inbox, send, read, reply, forward,
   label, thread, and attachment flows.
4. Add [webhooks.md](references/webhooks.md) or
   [websockets.md](references/websockets.md) only when polling is not enough.

## Pitfalls

- Prefer `AGENTMAIL_API_KEY` over `--api-key`.
- Never expose `AGENTMAIL_API_KEY` in prompts, logs, URLs, or committed files.
- Use stable `client_id` values for retried create operations.
- Prefer `extracted_text` or `extracted_html` for LLM input when present.
- React to `message.received`, not messages the agent sent.

## Verification

```bash
agentmail inboxes list --format json
```
