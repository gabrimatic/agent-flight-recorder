# Contributing

Run the test suite before opening a pull request:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

Keep runtime dependencies at zero unless there is a strong reason. This project should stay easy to run in CI and old repositories.

Good contribution areas:

- better risk rules
- better language-specific test detection
- better CI examples
- better report rendering
- safer redaction
- clearer docs

Avoid opaque non-deterministic behavior in the core merge gate. Deterministic checks should remain the default.
