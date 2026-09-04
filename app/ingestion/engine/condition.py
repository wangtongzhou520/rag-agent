"""Pipeline 条件 JSON DSL。"""

import re
from typing import Any

from app.ingestion.schemas import IngestionContext


class ConditionEvaluator:
    def evaluate(self, condition: Any, context: IngestionContext) -> bool:
        if condition is None:
            return True
        if isinstance(condition, bool):
            return condition
        if isinstance(condition, str):
            return self._expression(condition, context)
        if not isinstance(condition, dict):
            return False
        if "all" in condition:
            return all(self.evaluate(item, context) for item in condition["all"])
        if "any" in condition:
            return any(self.evaluate(item, context) for item in condition["any"])
        if "not" in condition:
            return not self.evaluate(condition["not"], context)
        actual = self._read(str(condition.get("field", "")), context)
        expected = condition.get("value")
        operator = str(condition.get("operator", "eq")).strip().lower()
        try:
            if operator == "eq":
                return self._norm(actual) == self._norm(expected)
            if operator == "ne":
                return self._norm(actual) != self._norm(expected)
            if operator == "in":
                return self._norm(actual) in [self._norm(item) for item in expected]
            if operator == "contains":
                return self._norm(expected) in actual if isinstance(actual, str) else expected in actual
            if operator == "regex":
                return re.fullmatch(str(expected), str(actual or "")) is not None
            if operator in {"gt", "gte", "lt", "lte"}:
                left, right = float(actual), float(expected)
                return {"gt": left > right, "gte": left >= right, "lt": left < right, "lte": left <= right}[operator]
            if operator == "exists":
                return actual is not None
            if operator == "not_exists":
                return actual is None
        except (TypeError, ValueError):
            return False
        return False

    def _expression(self, value: str, context: IngestionContext) -> bool:
        match = re.fullmatch(r"\s*([\w.]+)\s*(==|!=)\s*(['\"])(.*?)\3\s*", value)
        if not match:
            return False
        actual = self._norm(self._read(match.group(1), context))
        expected = self._norm(match.group(4))
        return actual == expected if match.group(2) == "==" else actual != expected

    @staticmethod
    def _norm(value: Any) -> Any:
        return value.strip().lower() if isinstance(value, str) else value

    @staticmethod
    def _read(path: str, context: IngestionContext) -> Any:
        value: Any = context
        aliases = {"mimeType": "mime_type", "taskId": "task_id", "pipelineId": "pipeline_id"}
        for part in path.split("."):
            part = aliases.get(part, part)
            value = getattr(value, part, None) if not isinstance(value, dict) else value.get(part)
            if value is None:
                break
        return str(value) if hasattr(value, "value") else value
