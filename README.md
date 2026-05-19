<!-- README.md -->

# workflow-as-list

WORKFLOWASLIST is a language to describe agent task workflows.
Its syntax is [SYNTAX.ebnf](./SYNTAX.ebnf).

The syntax is independent of programming language and execution layer.
Any language can implement a WORKFLOWASLIST parser and runtime.
This repository is a Python prototype.
The workflow files can also run on CLI Code Agents such as:
- Opencode
- Claude Code
- GitHub Copilot CLI
- Codex

## Why

Agent interactions are non-deterministic.
A natural language instruction can produce different message sequences, different shell commands, and different costs across runs.
This makes debugging, maintenance, and caching difficult.

WORKFLOWASLIST extracts the deterministic part of an agent interaction.
This part includes the message structure, the shell sequences, and the dependency graph.
It puts them into a parseable, shareable, cacheable form.
A workflow written in WORKFLOWASLIST always produces the same message list, even though agent responses vary.

The result is an interaction that can be:

- debugged by replay and step inspection
- maintained through version control
- scheduled as a periodic task
- cached at the provider level for cost savings

Think of it as a script for agent message lists, the same way bash is a script for shell commands.

> [!NOTE]
> This document is written with LLM assistance.
> There may be language gaps or inaccuracies.
> If something is unclear, please ask on [Discussions](https://github.com/D7x7z49/workflow-as-list/discussions).

## Python implementation

This repository is a Python prototype for WORKFLOWASLIST. It contains three packages:

- [packages/wal-core](./packages/wal-core/README.md)
- [packages/wal-runtime](./packages/wal-runtime/README.md)
- [packages/wal-cli](./packages/wal-cli/README.md)

The runtime in packages/wal-runtime can work with Code Agent adapters such as opencode codex as its execution layer.
