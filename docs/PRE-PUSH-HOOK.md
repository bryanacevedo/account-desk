# Proposed pre-push hook

A proposal, not installed. It runs the docs gate before every push and stops the push when the README, PROJECT-STATUS or the docs have drifted from the code. The gate takes under a second and needs no database.

Save this as `.git/hooks/pre-push` and make it executable (`chmod +x .git/hooks/pre-push`):

```sh
#!/bin/sh
# Stop a push when the docs no longer match the code. See docs/PRE-PUSH-HOOK.md.
exec make docs-check
```

What it checks is described at the top of `scripts/docs_check.py`: no test-count number in the README, the migrations range, every environment variable the code reads documented, the decision count in PROJECT-STATUS, and the Updated date. Skip it once with `git push --no-verify`. The same checks run in the test suite (`tests/test_docs_check.py`), so CI catches a drift even where the hook is not installed.
