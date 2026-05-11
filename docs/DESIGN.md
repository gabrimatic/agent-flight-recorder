# Design

Agent Flight Recorder is small on purpose.

It avoids runtime dependencies so it can run in CI, inside old repositories, and on machines where package managers are already enough work. The implementation uses Python standard library APIs plus git.

## Architecture

Main modules:

- `cli.py`: argparse command surface and exit codes.
- `session.py`: session lifecycle, manifests, before/after snapshots, report writing.
- `snapshot.py`: local repository inventory and before/after comparison.
- `git.py`: git command helpers and diff parsing.
- `process_recorder.py`: wrapped command execution, stdout/stderr capture, command metadata.
- `risk.py`: deterministic risk engine.
- `secrets.py`: local redaction and possible-secret detection.
- `report.py`: markdown report rendering.
- `config.py`: default config, loading, validation, deep merge.

## Session modes

### Manual

`afr start` creates an active session and captures a before-inventory. `afr run -- <command>` records commands. `afr stop` captures the after-inventory, compares changes, runs the risk engine, and writes the manifest and report.

### Wrapped command

`afr start -- <command>` captures the before-inventory, runs one command, captures the after-inventory, runs risk analysis, and exits with the child command exit code.

Command metadata is stored in a publishable form. `argv` and the normalized command string are redacted before they are written to manifests or markdown reports. The original argv is used only to launch the child process.

Captured stdout and stderr are drained through bounded in-memory buffers, redacted, then written to log files. The default cap is `max_command_output_bytes` per stream. Large command output cannot grow memory without a visible truncation marker.

### Analysis

`afr analyze` does not need a before-inventory. It asks git for the diff against a base ref and runs the risk engine. This is the GitHub Actions path.

Explicit base refs are fail-closed. If git cannot diff against the requested ref, `afr` exits with a clear error instead of falling back to a smaller working-tree-only analysis.

## Why Inventory Exists

Git diff works well in CI, but it is not enough for a local agent session. A session can create untracked files, generated artifacts, symlinks, or binary files. The inventory catches those, while git diff still handles added-line risk checks.

## Why Deterministic Rules Come First

The merge gate should be predictable. A future hosted product could add generated explanations, but the default gate should not depend on non-deterministic behavior.

## Manifest schema

The manifest is JSON and intentionally readable. Important sections:

- `repository`: branch, head, before/after status.
- `commands`: redacted argv, redacted normalized command string, exit code, timestamps, output paths, truncation flags.
- `files.changed`: path, status, size, binary marker.
- `risk`: score, level, findings, summary.
- `reports`: generated report paths.

## Exit codes

- `0`: success.
- `1`: verify failed.
- `2`: CLI/config/git/session error.
- `130`: interrupted.

## Known constraints

`afr` cannot observe commands run outside the recorder. That boundary is deliberate. Transparent shell recording is possible, but it is invasive, shell-specific, and fragile.

Local inventory hashes large files only up to `max_hash_bytes` for performance. For files whose hashes are truncated, inventory comparison also uses modification time so same-size edits beyond the hash cap are still surfaced for review.
