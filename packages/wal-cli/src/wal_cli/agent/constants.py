# packages/wal-cli/src/wal_cli/agent/constants.py

# Default max_tokens for Anthropic API calls when the caller does not
# specify an explicit value. Anthropic requires max_tokens on every
# messages.create() / messages.parse() request.
ANTHROPIC_DEFAULT_MAX_TOKENS = 4096
