.PHONY: check test

check:
	uv run pre-commit run --all-files

test:
	uv sync --all-packages
	uv run python -m pytest
