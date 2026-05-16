# Agent Shell - Project Guidelines

## Communication norms

PR and issue conversations are human relationships. The maintainer prefers
talking directly to humans.

When contributing:

- Write your own PR descriptions and issue comments. Don't have AI generate them.
- If you used AI to research something, summarize the findings in your own words
  and give your level of endorsement rather than pasting AI output verbatim.
  Concise, human-written summaries save the maintainer from having to parse
  lengthy generated text.
- Review all code in your PR yourself and vouch for its quality.

## Contributing

This is an Emacs Lisp project. See [CONTRIBUTING.org](CONTRIBUTING.org) for style
guidelines, code checks, and testing. Please adhere to these guidelines.

### Before submitting a PR

1. File a feature request first to discuss the proposal (see CONTRIBUTING.org).
2. Check out similar existing features and replicate their patterns.
3. Run `M-x checkdoc` and `M-x byte-compile-file` before pushing.
4. Add tests if you're adding new functionality.

### Key conventions worth repeating from CONTRIBUTING.org

- **Maps**: use alists with keyword symbols, access via `map.el`. Avoid plists
  and hashtables unless there's a strong reason not to.
- **State**: new fields go in `agent-shell--make-state` (line 717 of agent-shell.el),
  use `:kebab-case` keywords. New features should add their state keys here for
  a centralized view of available values.
- **Protocol data**: ACP protocol messages use camelCase (e.g. `'totalTokens`).
  Internal Elisp state uses `:kebab-case` (e.g. `:total-tokens`). This distinction
  makes it easy to spot what's protocol vs internal data.
- **Function definitions**: prefer `cl-defun` with named parameters (`&key`).
- **Control flow**: flatten `when/let` over nested blocks; avoid `let*/when-let*`
  unless bindings depend on each other. Use boolean guard clauses as bindings in
  `when-let` instead of nested `when-let`.
- **Docstrings**: include concrete input/output examples for readability.
- **Comments**: no LLM-generated comments or emojis in code. Remove comments that
  restated the obvious or reference "previous code".
- **Files**: substantial new functionality belongs in its own file (e.g.
  `agent-shell-completion.el`). Keep the `agent-shell--` prefix for internal
  functions across files.
- **PRs**: keep small and focused; no unrelated whitespace/formatting changes.

## Codebase overview

### Directory structure

```
agent-shell.el              # Core mode, state machine, event system, initialization, shell (7172 lines)
agent-shell-*.el            # Feature modules — see table below for specifics
tests/                      # Elisp unit tests + traffic capture files
images_bk/                  # Agent icon assets (SVG)
CONTRIBUTING.org            # Style guide and contribution process
AGENTS.md                   # Project guidelines (this file)
```

### Core architecture patterns

**State**: `agent-shell--state` is a buffer-local plist-style alist created by
`agent-shell--make-state` (line 717). All buffer-local state flows through this
single structure. It tracks: agent config, ACP client, session info, tool calls,
event subscriptions, idle timer, active/pending requests, and token usage stats.

**Events**: The event system (`agent-shell-subscribe-to`, `agent-shell--emit-event`)
is the primary communication channel between components. Events carry an `:event`
symbol and optional `:data` alist. Event types include:

- **Initialization**: `init-started`, `init-client`, `init-subscriptions`,
  `init-handshake`, `init-session`, `init-finished`, `prompt-ready`
- **Session**: `tool-call-update`, `file-write`, `permission-request`,
  `permission-response`, `turn-complete`, `session-title-changed`,
  `input-submitted`, `idle`
- **General**: `error`, `clean-up`

When adding new events, document them in the docstring of `agent-shell-subscribe-to`.

**ACP protocol**: Communication with agents happens via the Agent Client Protocol
(ACP). The ACP client is created by `acp-make-client` and managed through the
state's `:client` key. Each agent integration (Claude Code, Gemini CLI, Codex, etc.)
provides its own `agent-shell--make-*` function that configures the client.

**Data flow** — the event system and ACP traffic persistence are two completely
independent data pipelines:

```
                                  agent-shell event system
                                          │
                     agent-shell--emit-event (event + optional data)
                                          │
                      ┌────────────────────┼──────────────────┐
                      │                    │                  │
               event subscribers    enriched event data   UI/viewport
               (callbacks)          (never persisted)     updates
```

```
                                  ACP traffic persistence
                                          │
                     acp-traffic-log-traffic (direction, kind, message)
                                          │
                     ┌────────────────────┼────────────────────┐
                     │                    │                    │
               traffic buffer       advice writes to      analysis
               (in-memory)         per-agent JSONL       script
                                   file (raw JSON-RPC,
                                   enabled by knob)
```

Event data (enriched, internal) never touches the JSONL file. The JSONL file
(raw JSON-RPC) never passes through the event system. Enrichment from raw
traffic happens ad-hoc in the analysis script.

**Transcript system**: Per-session markdown transcripts are managed by functions
starting at line 6774 (`agent-shell--append-transcript`,
`agent-shell--make-transcript-tool-call-entry`). Path generation is driven by
the customizable `agent-shell-transcript-file-path-function` which defaults to
storing in `.agent-shell/transcripts/`.

**UI fragments**: The UI layer (`agent-shell-ui.el`) uses a fragment model with
`namespace-id` and `block-id` identifiers. Fragments have `label-left`,
`label-right`, and `body` sections that can be collapsed/expanded via text
properties and TAB navigation. Key function: `agent-shell-ui-update-fragment`.

**Mode setup**: New buffers initialize in `agent-shell--mode-setup` which runs
the ACP client init, session bootstrap, and subscriptions pipeline before firing
`agent-shell-mode-hook`. This is the right place for any per-buffer initialization
hooks or subscriptions.

### Key files by responsibility

| File | Purpose | Lines |
|------|---------|-------|
| `agent-shell.el` | Core: mode, state machine, event system, shell commands, permissions, completion, sessions, transcript, transients | 7172 |
| `agent-shell-ui.el` | Fragment model: insert/update/delete UI blocks, collapsible sections, TAB navigation | 699 |
| `agent-shell-viewport.el` | Viewport interaction layer — separate display buffer for agent output | 1325 |
| `agent-shell-usage.el` | Token usage tracking and cost display | 256 |
| `agent-shell-completion.el` | Tab completion in shell input | 127 |
| `agent-shell-diff.el` | Diff display for file write tool calls | 226 |
| `agent-shell-github.el` | GitHub PR/issue integration via CLI | 135 |
| `agent-shell-anthropic.el` | Anthropic provider client setup | 247 |
| `agent-shell-openai.el` | OpenAI/Codex provider client setup | 253 |
| `agent-shell-google.el` | Google/Gemini CLI provider client setup | 276 |
| `agent-shell-hermes.el` | Hermes agent integration | 120 |
| `agent-shell-qwen.el` | Qwen provider client setup | 180 |
| `agent-shell-mistral.el` | Mistral provider client setup | 191 |
| `agent-shell-goose.el` | Goose provider client setup | 177 |
| `agent-shell-opencode.el` | OpenCode provider client setup | 195 |
| `agent-shell-kimi.el` | Kimi provider client setup | 133 |
| `agent-shell-kiro.el` | Kiro provider client setup | 133 |
| `agent-shell-auggie.el` | Auggie provider client setup | 157 |
| `agent-shell-cline.el` | Cline provider client setup | 113 |
| `agent-shell-cursor.el` | Cursor provider client setup | 115 |
| `agent-shell-devcontainer.el` | Dev/container environment support | 71 |
| `agent-shell-droid.el` | Droid provider integration | 213 |
| `agent-shell-experimental.el` | Experimental/unstable features | 159 |
| `agent-shell-heartbeat.el` | Agent heartbeat/keepalive mechanism | 114 |
| `agent-shell-acp-traffic.el` | Raw ACP traffic persistence to JSONL | 80 |
| `agent-shell-active-message.el` | Active message tracking in session | 57 |
| `agent-shell-pi.el` | Pi provider integration | 134 |
| `agent-shell-project.el` | Project-level configuration/context | 102 |
| `agent-shell-styles.el` | UI styling helpers | 165 |
| `agent-shell-worktree.el` | Git worktree support for sessions | 138 |

### Testing

Tests live under the `tests/` directory. Opening any test file registers
`M-x agent-shell-run-all-tests`. Current test files:

```
tests/agent-shell-anthropic-tests.el
tests/agent-shell-command-prefix-tests.el
tests/agent-shell-devcontainer-tests.el
tests/agent-shell-diff-tests.el
tests/agent-shell-openai-tests.el
tests/agent-shell-tests.el         # Main test suite (largest file)
```

Traffic capture files in `tests/` record real ACP protocol exchanges for
reproducible testing.
