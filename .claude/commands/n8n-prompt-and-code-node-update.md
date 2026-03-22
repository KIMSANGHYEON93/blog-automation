---
name: n8n-prompt-and-code-node-update
description: Workflow command scaffold for n8n-prompt-and-code-node-update in blog-automation.
allowed_tools: ["Bash", "Read", "Write", "Grep", "Glob"]
---

# /n8n-prompt-and-code-node-update

Use this workflow when working on **n8n-prompt-and-code-node-update** in `blog-automation`.

## Goal

Update or enhance n8n workflow prompts and code nodes to improve content quality gates, prompt requirements, or workflow logic.

## Common Files

- `n8n/prompts/prompt_a_terminology.md`
- `n8n/prompts/prompt_b_comparison.md`
- `n8n/prompts/prompt_c_troubleshooting.md`
- `n8n/prompts/prompt_d_verification.md`
- `n8n/code_nodes/*.js`
- `n8n/workflow_complete.json`

## Suggested Sequence

1. Understand the current state and failure mode before editing.
2. Make the smallest coherent change that satisfies the workflow goal.
3. Run the most relevant verification for touched files.
4. Summarize what changed and what still needs review.

## Typical Commit Signals

- Edit one or more prompt markdown files in n8n/prompts/ (e.g., to raise content length, add new sections, or clarify instructions)
- Edit or add code node JS files in n8n/code_nodes/ (e.g., to add validation, parsing, or enrichment logic)
- Update n8n/workflow_complete.json to sync with new code nodes or prompt logic

## Notes

- Treat this as a scaffold, not a hard-coded script.
- Update the command if the workflow evolves materially.