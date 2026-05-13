# packages/wal-core/src/wal_core/constants.py

from enum import Enum

# Line prefixes
PREFIX_COMMENT = "#"
PREFIX_VARIABLE = ":"
PREFIX_STEP = "-"
PREFIX_IMPORT = ">"

# Control symbols
SYMBOL_EQUALS = "="
SYMBOL_AT = "@"
SYMBOL_SHELL = "!"
SYMBOL_QUESTION = "?"
SYMBOL_DOT = "."

# Tag symbols
TAG_OPEN = "("
TAG_CLOSE = ")"

# Substitution symbols
SUBSTITUTION_START = "${"
SUBSTITUTION_END = "}"
SUBSTITUTION_PIPE = "!"

# Common characters
INDENT_UNIT = "  "


class StepMode(str, Enum):
    PLAIN = "plain"
    SHELL = "shell"
    QUESTION = "question"
