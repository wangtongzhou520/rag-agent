from datetime import timedelta

from fastapi.routing import APIRoute

from app.admin.dashboard import DashboardService, _p95, _rate, parse_window, router
from app.system.auth.deps import require_admin


def test_window_parser_preserves_valid_label_and_falls_back() -> None:
    parsed = parse_window("12H", "24h")
    assert parsed.label == "12H"
    assert parsed.duration == timedelta(hours=12)

    assert parse_window("bad", "7d").label == "7d"
    assert parse_window("0h", "24h").duration == timedelta(hours=24)


def test_dashboard_rounding_and_p95_contract() -> None:
    assert _rate(1, 3) == 33.3
    assert _rate(0, 0) == 0.0
    assert _p95([]) == 0
    assert _p95(list(range(1, 101))) == 95


def test_dashboard_bucket_defaults_and_gap_shape() -> None:
    assert DashboardService._granularity(None, timedelta(hours=48)) == "hour"
    assert DashboardService._granularity("invalid", timedelta(days=7)) == "day"
    assert DashboardService._series(
        "会话数", ["a", "b"], {"a": 1, "b": 2}, {"b": 3}
    ) == {
        "name": "会话数",
        "points": [{"ts": 1, "value": 0}, {"ts": 2, "value": 3}],
    }


def test_all_dashboard_routes_require_admin() -> None:
    assert len(router.routes) == 3
    for route in router.routes:
        assert isinstance(route, APIRoute)
        assert require_admin in {item.call for item in route.dependant.dependencies}
