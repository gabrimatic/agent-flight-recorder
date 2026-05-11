# Risk rules

The risk engine is deterministic. It surfaces review risk; it does not prove correctness.

## Levels

- low: 0-20
- medium: 21-50
- high: 51-79
- critical: 80-100

Set thresholds in `.agent-flight/config.json`.

## Built-in findings

### `risk-zone-auth`

Triggers when changed paths match auth, login, session, JWT, OAuth, permission, RBAC, ACL, or policy patterns.

### `risk-zone-payments`

Triggers when changed paths match billing, payment, Stripe, PayPal, checkout, invoice, subscription, or pricing patterns.

### `risk-zone-database`

Triggers on migrations, schema files, Prisma schema, Alembic, Liquibase, and similar paths.

### `risk-zone-crypto-secrets`

Triggers on cryptography, encryption, decryption, token, secret, keychain, keystore, and vault paths.

### `risk-zone-infrastructure`

Triggers on Docker, CI, Terraform, Kubernetes, YAML, and deployment-sensitive files.

### `dependency-file-changed`

Triggers on dependency manifests and lockfiles.

### `source-without-recorded-tests`

Triggers when source files changed but no successful recorded test command was found.

A successful test command is any recorded command whose text matches configured patterns and exits with code zero.

Default patterns include direct test runners and project task wrappers such as `pytest`, `npm test`, `make test`, `make check`, `just test`, `task test`, `tox`, and `nox`. The detector also recognizes task-runner targets with options, such as `make -C app test`.

### `source-without-test-file-change`

Triggers when source changed but no test files changed. This is medium severity because existing tests may already cover the behavior.

### `possible-secret-leak`

Triggers when changed files contain patterns resembling API keys, private key blocks, database URLs with passwords, JWTs, GitHub tokens, Slack tokens, `sk-` style keys, AWS access keys, or generic secret assignments.

Previews are redacted.

### `dangerous-added-lines`

Triggers on added diff lines containing suspicious destructive patterns such as `DROP TABLE`, `TRUNCATE TABLE`, `DELETE FROM table;`, `chmod 777`, `curl | sh`, or dangerous `rm -rf` patterns.

Untracked added files are scanned as added content when they appear in the manifest.

### `command-failed`

Triggers when a recorded command exits non-zero.

### `no-command-log`

Triggers when changed files exist but no command was recorded.

## Customization

Edit `.agent-flight/config.json` to add or remove risk zones, test command patterns, test file globs, source extensions, dependency files, and thresholds.
