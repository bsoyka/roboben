"""Helpers that don't fit into another category."""

from typing import Optional


# pylint: disable=invalid-name
def find_nth_occurrence(string: str, substring: str, n: int) -> Optional[int]:
    """Return index of `n`th occurrence of `substring` in `string`, or None if
    not found.
    """
    index = 0
    for _ in range(n):
        index = string.find(substring, index + 1)
        if index == -1:
            return None
    return index
