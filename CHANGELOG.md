# Changelog

All notable changes to Agent Flight Recorder are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## 0.1.0

Initial release.

Agent Flight Recorder (`afr`) records local, deterministic receipts for coding-agent code changes, so reviewers get evidence about what an agent did before trusting a delegated result.

### Added

- `afr` CLI with `init`, `start`, `run`, `stop`, `analyze`, `verify`, `report`, and `doctor` commands.
- Session recording under a local `.agent-flight/` folder: changed files, redacted command lines, exit codes, and bounded stdout/stderr logs.
- Deterministic, local risk engine that produces a 0-100 score with low/medium/high/critical severity floors, covering auth, payment, database, crypto, secret, infrastructure, CI, and dependency changes, possible secret leaks, dangerous added lines, and missing test evidence.
- Merge-gate verification via `afr verify` with `--max-score`, `--max-level`, `--require-tests-for-high-risk`, and `--require-command-log`.
- `afr analyze` for CI or local diff analysis with base-ref fallbacks.
- GitHub Action for running the recorder on pull requests.
- Markdown and JSON reports with local secret redaction and no generated-by footers.
- Zero runtime dependencies beyond Python 3.10+ and git.
