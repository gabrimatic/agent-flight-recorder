# Basic Report Example

Create a report from a recorded command:

```bash
afr start -- python scripts/change.py
afr report
```

The report includes:

- risk score
- session metadata
- changed files
- command logs
- risk findings
- suggested merge gate
