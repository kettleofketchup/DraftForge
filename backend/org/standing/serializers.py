from typing import Any

from org.standing.types import Leaderboard, LeaderboardRow, Metric, TrackInfo


def metric_data(metric: Metric) -> dict[str, Any]:
    return {
        "key": metric.key,
        "label": metric.label,
        "format": metric.format,
        "periodic": metric.periodic,
        "default": metric.default,
    }


def track_info_data(info: TrackInfo) -> dict[str, Any]:
    return {
        "key": info.key,
        "label": info.label,
        "metrics": [metric_data(m) for m in info.metrics],
        "can_view_rows": info.can_view_rows,
        "can_view_own": info.can_view_own,
        "board_open": info.board_open,
        "can_manage": info.can_manage,
    }


def row_data(row: LeaderboardRow) -> dict[str, Any]:
    return {
        "member": dict(row.member),
        "value": row.value,
        "sample": row.sample,
        "status": row.status,
    }


def leaderboard_data(board: Leaderboard) -> dict[str, Any]:
    return {
        "track": board.track,
        "metric": metric_data(board.metric),
        "period": board.period,
        "total": board.total,
        "rows": [row_data(r) for r in board.rows],
        "rows_visible": board.rows_visible,
        "own_row": row_data(board.own_row) if board.own_row is not None else None,
    }
