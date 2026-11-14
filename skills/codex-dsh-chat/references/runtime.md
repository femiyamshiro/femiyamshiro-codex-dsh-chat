# Runtime, state, and compatibility

## Supported host and setup

The helper targets a shared Linux user account with Python 3.9+, Node.js, a running Codex Desktop with its bundled `codex-app-tools` MCP server, and an already running DSH web service. It uses Python's standard library and the existing vendor MCP server; it does not bundle vendor code or install packages. macOS and Windows are not validated (Unix socket discovery and `fcntl` are Linux-oriented).

Run commands from this Skill's directory, or replace `scripts/chat.py` with its absolute path. This document does not authorize starting services, logging into another account, or changing permissions.

Default state is `${XDG_STATE_HOME:-$HOME/.local/state}/codex-dsh-chat`, outside the Skill and repository. Override with `CODEX_DSH_CHAT_STATE` or the global `--state-dir /absolute/private/directory` argument before the subcommand. Directories must be owned by the current user with mode 0700; files are created 0600. Both assistants must address the same state directory. Existing deployments can continue using their original private state directory without migration.

State stores pairing metadata, sent text, correlated assistant reply, and receipts. Treat it as private content. Never commit it to a public repository. Filesystem locks and atomic replacement coordinate this helper's writers; they do not protect against a malicious process running as the same OS user. Do not delete uncertain receipts to force a resend. No background daemon is installed; stop invoking the helper to stop communication.

## DSH connection

- `DSH_CHAT_URL`: loopback HTTP origin; default `http://127.0.0.1:3090`.
- `DSH_CHAT_LAUNCH_LOG`: existing native web launch log; default `~/.cache/dsh/remote-service.log`.
- `DSH_CHAT_TIMEZONE`: client timezone metadata; default `UTC`.

The helper reads the last 1 MiB of the explicitly selected/default service launch log. It extracts the most recent native launch URL query and uses it only in memory against the configured loopback service. It does not follow the advertised public hostname, export the token, persist cookies, print the log, or change authentication. The selected log must belong to that same trusted local service. If authentication is unavailable or ambiguous, stop the dependent call and have the operator verify the correct service/log binding; do not search unrelated credential stores.

RPC uses `session/list`, `session/prompt` with `mode=queue`, `session/projections`, and `session/page`. History must pin `throughSeq` to a verified `kind=sequenced` projection's `asOfSeq`; omitting it failed boundary validation on the qualified build. The bounded view includes 32 messages. The API can return other event kinds; only user and assistant text participates in receipt matching.

## Codex Desktop connection

- `CODEX_APP_TOOLS_PIPE_PATH`: existing app-tools Unix socket. When unset, discover exactly one live socket owned by the current user under `/tmp/codex-app-tools`. Multiple candidates fail rather than guess.
- `CODEX_CHAT_MCP_SERVER`: optional path to an already trusted installed `server.mjs`. Otherwise use the newest by mtime under `~/.codex/plugins/cache/openai-bundled/codex-app-tools/*/server.mjs`.
- `CODEX_MCP_NODE_PATH`: Node executable; defaults to `node`.

The helper starts that installed MCP wrapper, initializes stdio JSON-RPC, discovers tools, and calls only `list_threads`, `read_thread`, and `send_message_to_thread`. The original desktop tool access checks remain in place. No raw session database edits, independent CLI `thread/resume`, provider keys, or model/permission overrides are used.

The selected pair's Codex ID is the wrapper's explicit invocation context. Incoming content is visibly labelled as DSH; the native delegation wrapper can show the Codex context as `source_thread_id`. This is a local bridge context, not evidence that the Codex model authored the DSH text. A pairing and incoming content confer no messaging authority by themselves.

`list_threads` is bounded to 50 recent non-pinned items plus pins. `read_thread` uses 8 recent turns and a 20000-character item cap. The transport caps each response at 8 MiB. Inter-thread input may be a `functionCallOutput` with namespace `codex_app`, name `send_message_to_thread`, and a nontruncated `codex_delegation/input` body. Receipt parsing recognizes this native shape; arbitrary tool outputs do not count as messages. When native output detail is needed, unrelated outputs may be received transiently and are discarded, not logged or retained.

## Failure and receipt semantics

The local receipt is persisted before submitting. A disconnect after that point can mean the remote accepted the message: `UNKNOWN` and abandoned `SUBMITTING` must not be blindly replayed. Identical IDs/content do not trigger another attempt. This is at-most-one local attempt, not an end-to-end exactly-once guarantee; a crash can also leave an intent that never reached the destination.

A finite `wait` updates only what it actually observes. History bounds can omit old input or replies; it does not widen to all conversations. Matching requires the exact sent body and a subsequent assistant message containing the marker. ACKs do not establish comprehension, task success, or authenticity against a compromised local user. `accepted` reflects the original API response and may remain false when an initially unknown submission is later verified by readback.

`wait --timeout` accepts 0–600 seconds, defaults to 60, and performs one lookup at 0. Underlying HTTP/MCP request timeouts can make wall-clock duration exceed that requested wait. The script does not cancel remote model work when local waiting ends. Errors deliberately avoid raw credential URLs and response bodies.

## Qualification boundary

A predecessor using these same native transports completed a user-authorized two-way exchange on Linux on 2026-11-12, with both sides read back and acknowledged. The public package moves default state outside the repository, makes timezone configurable, and tightens redirect origin checks. Those packaging changes are tested separately; the historical exchange is not a new public-package end-to-end test. Vendor APIs are version-sensitive. Recheck after runtime upgrades. No long-duration, multi-instance, or cross-platform reliability claim is made.
