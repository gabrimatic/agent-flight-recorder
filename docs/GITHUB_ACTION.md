# GitHub Action usage

Agent Flight Recorder includes a composite action at `action.yml`.

## Basic workflow

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
```

## Strict workflow

```yaml
      - uses: gabrimatic/agent-flight-recorder@v0
        with:
          max_score: "50"
          require_tests_for_high_risk: "true"
```

## Recorded-session workflow

Use this when a previous step has produced or downloaded a manifest from a recorded `afr start` or `afr run` session:

```yaml
      - uses: gabrimatic/agent-flight-recorder@v0
        with:
          manifest: path/to/manifest.json
          max_score: "50"
          require_tests_for_high_risk: "true"
          require_command_log: "true"
```

When `manifest` is set, the action skips fresh diff analysis, renders the markdown report from that manifest, and verifies the manifest directly.

## Inputs

- `base_ref`: optional git ref. Defaults to `origin/$GITHUB_BASE_REF` for pull requests.
- `manifest`: optional existing manifest path. When set, analysis is skipped and this manifest is verified.
- `max_score`: fail when risk score is greater than this value. Default: `79`.
- `require_tests_for_high_risk`: fail high/critical manifests with no recorded successful test command.
- `require_command_log`: fail changed manifests with no recorded command log.
- `output`: markdown output path. Default: `.agent-flight/pr-report.md`.

Use `fetch-depth: 0` with `actions/checkout`. Explicit base refs must resolve; if the ref is missing, the action fails instead of silently analyzing a partial diff.

## Important note about command logs in CI

`afr analyze` can analyze a PR diff, but it cannot know what commands a developer ran locally. If you enable `require_command_log`, pass a recorded manifest with the `manifest` input. For many teams, the best initial CI setting is `require_command_log: false`.
