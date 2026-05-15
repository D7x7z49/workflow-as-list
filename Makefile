.PHONY: check test release

check:
	uv run pre-commit run --all-files

test:
	uv sync --all-packages
	uv run python -m pytest

release-try-run:
	git fetch --tags
	uv run python scripts/auto_version.py --dry-run --stage dev
	uv run python scripts/auto_version.py --dry-run --stage alpha
	uv run python scripts/auto_version.py --dry-run --stage beta
	uv run python scripts/auto_version.py --dry-run --stage rc
	uv run python scripts/auto_version.py --dry-run --stage stable
release-alpha:
	git fetch --tags
	uv run python scripts/auto_version.py --stage alpha
release-beta:
	git fetch --tags
	uv run python scripts/auto_version.py --stage beta
release-rc:
	git fetch --tags
	uv run python scripts/auto_version.py --stage rc
release:
	git fetch --tags
	uv run python scripts/auto_version.py

gen-commit-msg:
	uv run wal-cli run workflow ./example/git/commit/gen-git-commit-message.wal --agent test
