"""LRC lyrics parsing utilities for the API endpoint.

Parses standard LRC format into (time_ms, text) pairs.
No dependency on karaoke_workflows — intentionally lightweight so
the endpoint is available in SERVE_MODE without heavy imports.
"""

import re
from typing import List, Tuple

# LRC metadata tags to skip (e.g. [ti:Title], [ar:Artist])
_METADATA_RE = re.compile(r"^\[(?:ti|ar|al|by|offset|length|re|ve):", re.IGNORECASE)

# Standard LRC timestamp: [MM:SS.CC] or [MM:SS.XX]
_TIMESTAMP_RE = re.compile(r"^\[(\d+):(\d+(?:\.\d+)?)\](.*)")


def parse_lrc(lrc: str) -> List[Tuple[int, str]]:
  """Parse an LRC string into a list of (time_ms, text) tuples.

  Skips metadata tags and blank lines. Returns lines in timestamp order.

  Args:
    lrc: Raw LRC content string.

  Returns:
    List of (time_ms, text) tuples, sorted by time_ms.
  """
  result: List[Tuple[int, str]] = []

  for line in lrc.splitlines():
    line = line.strip()
    if not line:
      continue
    if _METADATA_RE.match(line):
      continue

    m = _TIMESTAMP_RE.match(line)
    if not m:
      continue

    minutes = int(m.group(1))
    seconds = float(m.group(2))
    text = m.group(3).strip()

    if not text:
      continue

    time_ms = int(minutes * 60_000 + seconds * 1_000)
    result.append((time_ms, text))

  result.sort(key=lambda x: x[0])
  return result
