.PHONY: check test release

check:
	uv run pre-commit run --all-files

test:
	uv sync --all-packages
	uv run python -m pytest

release-try-run:
	uv run python scripts/auto_version.py --dry-run
release-test:
	git tag -l 'd49-*' | xargs git tag -d
	uv run python scripts/auto_version.py
release:
	uv run python scripts/auto_version.py
