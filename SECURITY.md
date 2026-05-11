# Security policy

Agent Flight Recorder is a local CLI. It does not make network calls and has no runtime third-party dependencies.

## Sensitive data handling

- Command output is redacted by default before being written to logs.
- Recorded command argv and normalized command strings are redacted before they are written to manifests or reports.
- Captured stdout and stderr are bounded by `max_command_output_bytes`; truncated logs include an explicit marker.
- Possible secret findings use redacted previews.
- Generated session data is ignored by `.agent-flight/.gitignore`.
- Reports may still include file paths, command names, branch names, and other sensitive project metadata.

Inspect reports before publishing them.

## Reporting vulnerabilities

Open a private security advisory or contact the maintainer privately if this repository has a security issue. Do not include real secrets in public issues.

## Scope

The tool is not a sandbox. It runs the commands you pass to it. Do not run untrusted commands through it expecting containment.
