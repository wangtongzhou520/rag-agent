"""确定性的 JSON Pointer 变更 Diff。"""

from typing import Any

_MISSING = object()


def _escape(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def collect_diff(before: Any, after: Any) -> list[dict]:
    changes: list[dict] = []

    def collect(path: str, left: Any, right: Any) -> None:
        if left is not _MISSING and right is not _MISSING and left == right:
            return
        if isinstance(left, dict) and isinstance(right, dict):
            for key in sorted(set(left) | set(right)):
                collect(
                    f"{path}/{_escape(str(key))}",
                    left.get(key, _MISSING),
                    right.get(key, _MISSING),
                )
            return
        if isinstance(left, list) and isinstance(right, list):
            for index in range(max(len(left), len(right))):
                collect(
                    f"{path}/{index}",
                    left[index] if index < len(left) else _MISSING,
                    right[index] if index < len(right) else _MISSING,
                )
            return
        changes.append(
            {
                "field": path or "/",
                "before": None if left is _MISSING else left,
                "after": None if right is _MISSING else right,
            }
        )

    collect("", before, after)
    return changes
