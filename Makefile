.PHONY: check

check:
	uv run pre-commit run --all-files
