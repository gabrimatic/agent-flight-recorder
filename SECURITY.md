# Security policy

Agent Flight Recorder is a local developer tool. It does not make network calls and has no runtime third-party dependencies.

## Sensitive data handling

- Command output is redacted by default before being written to logs.
- Possible secret findings use redacted previews.
- Generated session data is ignored by `.agent-flight/.gitignore`.
- Reports may still include file paths, command names, branch names, and other sensitive project metadata.

Before publishing a report, inspect it.

## Reporting vulnerabilities

Open a private security advisory or contact the maintainer privately if this repository has a security issue. Do not include real secrets in public issues.

## Scope

The tool is not a sandbox. It runs commands you ask it to run. Do not run untrusted commands through it expecting containment.
