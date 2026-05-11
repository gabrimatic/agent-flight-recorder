# Agent Flight Recorder

Black-box recorder for coding-agent code changes.

Agent Flight Recorder (`afr`) records what changed during a coding-agent session, what commands were run, which files were touched, whether tests were recorded, and which risky areas need human review before merge.

It is built for the new workflow where a developer says “let the agent implement this,” then needs receipts before trusting the result.

## What it does

`afr` creates a local `.agent-flight` folder containing:

```text
.agent-flight/
  config.json                 # tracked project config
  pr-report.md                # latest markdown report
  manifest.json               # latest machine-readable manifest
  sessions/<session-id>/
    manifest.json
    before-inventory.json
    after-inventory.json
    pr-report.md
    commands/
      cmd-0001.stdout.log
      cmd-0001.stderr.log
```

The manifest records:

- session id, branch, commit, start/end time
- redacted command lines run through the recorder
- command exit codes
- stdout/stderr logs, redacted by default and bounded by a configurable byte limit
- changed files
- binary files
- dependency manifest changes
- auth, payment, database, crypto, secret, infrastructure, and CI-sensitive changes
- possible secret leaks
- dangerous added lines such as destructive SQL or `curl | sh`
- whether a successful test command was recorded
- a risk score from 0 to 100

## What it does not pretend to do

Agent Flight Recorder is a review aid, not a proof of correctness.

It cannot observe commands that are run outside `afr`. If a developer runs `npm test` in another terminal without `afr run -- npm test`, the manifest will not know. It also cannot guarantee that code is safe, correct, non-malicious, or produced by the recorded process. The useful guarantee is narrower: it records the process you choose to run through it and produces deterministic review evidence.

## Install

From a checkout:

```bash
python afr.py doctor
```

As a Python package:

```bash
pip install .
afr doctor
```

Runtime dependencies: none beyond Python 3.10+ and git.

## Quick start

Inside a git repository:

```bash
afr init
```

Wrap a coding-agent command:

```bash
afr start -- agent-cli
```

Wrap a non-interactive command and capture logs:

```bash
afr start -- python scripts/refactor.py
```

Start a manual session:

```bash
afr start --note "auth refactor"
# do work
afr run -- python -m unittest
afr stop
```

Print the latest report:

```bash
afr report
```

Analyze the current diff in CI or locally:

```bash
afr analyze --base-ref origin/main --output .agent-flight/pr-report.md
afr verify --max-score 79
```

## Commands

### `afr init`

Creates `.agent-flight/config.json` and `.agent-flight/.gitignore`.

```bash
afr init
afr init --force
```

### `afr start`

Two modes exist.

Manual session:

```bash
afr start --session-id my-session --note "agent did auth migration"
# make changes
afr run -- python -m unittest
afr stop
```

Wrapped command session:

```bash
afr start -- python -c "from pathlib import Path; Path('x.py').write_text('print(1)')"
```

By default, wrapped commands have stdout/stderr captured and redacted. For interactive tools that need direct terminal access:

```bash
afr start --interactive -- agent-cli
```

When `--interactive` is used, the command inherits the terminal. The command line and exit code are still recorded, but stdout/stderr are not captured.

Recorded command metadata is redacted before it is written to the manifest. Secret-looking flag values such as `--api-key <value>`, `--token=<value>`, `PASSWORD=<value>`, and common key formats are replaced in reports and manifests. Captured stdout and stderr are capped by `max_command_output_bytes` in `.agent-flight/config.json`; truncated logs include an explicit `[afr: ... truncated ...]` marker.

### `afr run`

Runs and records a command inside an active manual session.

```bash
afr run -- npm test
afr run -- flutter test
afr run -- python -m unittest
```

### `afr stop`

Stops the active manual session, compares before/after repository inventory, runs the risk engine, writes the manifest, and writes `.agent-flight/pr-report.md`.

### `afr analyze`

Analyzes the current git diff without an active session. This is best for CI.

```bash
afr analyze --base-ref origin/main
afr analyze --output .agent-flight/pr-report.md
afr analyze --base-ref origin/main --json --output manifest.json
```

If no base ref is provided, `afr` tries `AFR_BASE_REF`, then `origin/main`, `origin/master`, `main`, `master`, then `HEAD~1`. If you pass a base ref explicitly, it must resolve; a typo fails instead of silently analyzing the wrong range.

### `afr verify`

Fails with exit code 1 if the manifest violates merge-gate rules.

```bash
afr verify --max-score 79
afr verify --max-level medium
afr verify --require-tests-for-high-risk
afr verify --require-command-log
```

`--max-score 79` means critical risk fails. `--max-score 50` means high and critical risk fail.

### `afr report`

Prints the latest markdown report, or writes markdown/JSON to a file.

```bash
afr report
afr report --format json
afr report --session-id afr-20260509-120000-abcd1234
afr report --output report.md
```

### `afr doctor`

Prints environment diagnostics.

```bash
afr doctor
afr doctor --json
```

## GitHub Action

Add this to `.github/workflows/agent-flight.yml`:

```yaml
name: Agent Flight Recorder

on:
  pull_request:

jobs:
  agent-flight:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
        with:
          fetch-depth: 0
      - uses: gabrimatic/agent-flight-recorder@v0
        with:
          max_score: "79"
          require_tests_for_high_risk: "false"
          require_command_log: "false"
```

For stricter teams:

```yaml
      - uses: gabrimatic/agent-flight-recorder@v0
        with:
          max_score: "50"
          require_tests_for_high_risk: "true"
```

To verify a pre-recorded session manifest instead of analyzing the current diff:

```yaml
      - uses: gabrimatic/agent-flight-recorder@v0
        with:
          manifest: path/to/manifest.json
          max_score: "50"
          require_tests_for_high_risk: "true"
          require_command_log: "true"
```

When `manifest` is set, the action skips `afr analyze`, renders the report from that manifest, and verifies the recorded commands. This is the mode to use when your team expects agent sessions to be recorded with `afr start` or `afr run`. `require_command_log` is too strict for normal PRs where only diff analysis is expected.

## Risk scoring

The risk engine is deterministic. It does not need a remote service.

Risk levels:

- low: 0-20
- medium: 21-50
- high: 51-79
- critical: 80-100

Signals include:

- source files changed without a recorded successful test command
- source files changed without test files changing
- auth/authorization/session/JWT/OAuth code changed
- billing/payment/subscription/pricing code changed
- database migrations or schema changed
- cryptography/secret/key-management code changed
- infrastructure, YAML, Docker, CI, Terraform, or Kubernetes files changed
- dependency manifests or lockfiles changed
- binary files changed
- large change sets
- possible secrets in changed files
- dangerous added lines
- failed recorded commands
- no command log

All rules can be adjusted in `.agent-flight/config.json`.

## Configuration

Default config is created by `afr init`.

Important keys:

```json
{
  "max_hash_bytes": 10485760,
  "max_text_scan_bytes": 2000000,
  "redact_command_output": true,
  "exclude_globs": [".git/**", ".agent-flight/**", "node_modules/**", "build/**"],
  "test_command_patterns": ["pytest", "npm test", "make test", "go test", "flutter test"],
  "test_file_globs": ["tests/**", "**/*.test.*", "**/*_test.*"],
  "risk_thresholds": {
    "medium": 21,
    "high": 51,
    "critical": 80
  }
}
```

Config validation is strict. List fields must contain strings, byte limits and thresholds must be integers, and each risk zone needs an `id` plus a string-list `patterns` value.

## Privacy and security

- Session data is local by default.
- `.agent-flight/sessions/`, `.agent-flight/manifest.json`, and active-session state are ignored by `.agent-flight/.gitignore`.
- Command stdout/stderr are redacted by default using local regex rules.
- Changed files are scanned locally for possible secrets.
- Secret findings include redacted previews only.
- No network calls are made by the tool.

If you commit generated reports, inspect them first. They may contain file paths, command lines, or other project-sensitive metadata.

## Edge cases handled

- Git repositories with unborn or detached HEADs.
- Manual sessions and one-shot wrapped sessions.
- Interactive commands with inherited terminal.
- Untracked files.
- Deleted files.
- Symlinks.
- Binary files.
- Large files with hash truncation.
- Missing config, with automatic default generation.
- Missing base refs in CI, with fallback refs.
- Explicit invalid base refs fail instead of falling back.
- Failed child commands, while still writing a manifest.
- Interrupted CLI, with exit code 130.

## Why this is different from code review bots

Most bots look only at the final diff.

Agent Flight Recorder records the surrounding process: what command was delegated, what changed, what validation ran, and what risky areas deserve human attention. It is provenance and merge-gate evidence for coding-agent development.

## Development

Run tests:

```bash
make test
```

Run the full local check:

```bash
make check
```

Package builds use `python -m build`; install `build` in your development environment if that module is missing.

Run directly from source:

```bash
PYTHONPATH=src python -m agent_flight_recorder doctor
```

## License

MIT.
