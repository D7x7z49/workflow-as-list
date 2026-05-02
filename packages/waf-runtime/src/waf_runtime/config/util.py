# packages/waf-runtime/src/waf_runtime/config/util.py

import re
import subprocess

_SUFFIXED_NUMBER_PATTERN_STR = r"^(\d+)([km]?)$"
_SUFFIXED_NUMBER_PATTERN = re.compile(_SUFFIXED_NUMBER_PATTERN_STR, re.IGNORECASE)


def parse_suffixed_number(s: str) -> int:
    s = s.strip().replace(",", "")
    match = _SUFFIXED_NUMBER_PATTERN.match(s)
    if not match:
        raise ValueError(
            f"Input '{s}' does not match the expected format of a number "
            f"optionally followed by 'k' or 'm' (pattern: {_SUFFIXED_NUMBER_PATTERN_STR})"
        )
    num = int(match.group(1))
    suffix = match.group(2).lower()
    if suffix == "k":
        return num * 1000
    if suffix == "m":
        return num * 1_000_000
    return num


def get_pass(entry: str) -> str:
    result = subprocess.run(["pass", "show", entry], capture_output=True, text=True, check=True)
    return result.stdout.strip()
