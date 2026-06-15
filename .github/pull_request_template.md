<!--
Thanks for contributing to awx-mcp!
Keep PRs focused — one logical change per PR.
-->

## Summary

<!-- What does this PR change, and why? -->

## Related issue

<!-- e.g. Closes #123. PRs without a linked issue may be asked to open one first. -->

## Type of change

- [ ] Bug fix (non-breaking change that fixes an issue)
- [ ] New tool / feature (non-breaking change that adds functionality)
- [ ] Breaking change (fix or feature that changes existing behavior)
- [ ] Docs only
- [ ] Refactor / chore

## Checklist

- [ ] My commits are signed off (`git commit -s`) per the [DCO](https://github.com/lycorp-jp/awx-mcp/blob/main/DCO.md). **Every** commit needs a `Signed-off-by` line.
- [ ] `uv run ruff check .` passes.
- [ ] `uv run pytest tests/ -v` passes.
- [ ] I added or updated tests for my change.
- [ ] I updated the docs (README.md / README.ko.md / README.ja.md) and the tool counts stay consistent (`uv run python scripts/check_doc_parity.py`).
- [ ] I updated `CHANGELOG.md` under the unreleased section.
- [ ] I did not commit secrets, tokens, or internal hostnames.

## Notes for reviewers

<!-- Anything reviewers should pay special attention to. -->
