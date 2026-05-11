# Design

Agent Flight Recorder is intentionally small and deterministic.

The tool avoids runtime dependencies so it can run inside CI, inside old repositories, and on developer machines without a package-manager fight. It uses Python standard library APIs plus git.

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

`afr start` creates an active session and captures a before-inventory. `afr run -- <command>` records commands. `afr stop` captures the after-inventory, compares changes, runs the risk engine, and writes outputs.

### Wrapped command

`afr start -- <command>` captures before-inventory, runs one command, captures after-inventory, runs risk analysis, and exits with the child command exit code.

### Analysis

`afr analyze` does not need a before-inventory. It asks git for the diff against a base ref and runs the risk engine. This is the right mode for GitHub Actions.

Explicit base refs are fail-closed. If git cannot diff against the requested ref, `afr` exits with a user-facing error instead of falling back to a smaller working-tree-only analysis.

## Why inventory instead of only git diff?

Git diff is excellent in CI but not enough for a local agent session because a developer may create untracked files, generated artifacts, symlinks, or binary files. The inventory approach catches these. Git diff is still used for added-line risk checks.

## Why deterministic rules first?

The first version should be trusted because it is predictable. A future hosted product could add generated explanations, but the base risk gate should not depend on non-deterministic behavior.

## Manifest schema

The manifest is JSON and intentionally human-readable. Important sections:

- `repository`: branch, head, before/after status.
- `commands`: argv, normalized command string, exit code, timestamps, output paths.
- `files.changed`: path, status, size, binary marker.
- `risk`: score, level, findings, summary.
- `reports`: generated report paths.

## Exit codes

- `0`: success.
- `1`: verify failed.
- `2`: user-facing CLI/config/git/session error.
- `130`: interrupted.

## Known constraints

`afr` cannot observe commands run outside the recorder. This is deliberate and documented. Recording shells transparently is possible but invasive, shell-specific, and fragile.
