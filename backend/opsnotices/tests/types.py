from pydantic import BaseModel

from opsnotices.registry import (
    NoticeCategory,
    NoticeSeverity,
    NoticeType,
    register_notice_type,
)


class AlertPayload(BaseModel):
    member_id: int
    reason: str


def _summary(payload: AlertPayload) -> str:
    return f"Member {payload.member_id}: {payload.reason}"


def _sample() -> AlertPayload:
    return AlertPayload(member_id=1, reason="sample")


def _dedupe(payload: AlertPayload) -> str:
    return f"member:{payload.member_id}"


def _test_type(
    key: str,
    category: NoticeCategory,
    severity: NoticeSeverity,
    dedupe: bool = True,
) -> NoticeType[AlertPayload]:
    return NoticeType(
        key=key,
        label=key,
        description=f"Test type {key}",
        category=category,
        default_severity=severity,
        payload=AlertPayload,
        summary=_summary,
        sample_payload=_sample,
        dedupe_key=_dedupe if dedupe else None,
    )


def register_test_types() -> None:
    register_notice_type(
        _test_type("test.alert", NoticeCategory.URGENT, NoticeSeverity.WARNING)
    )
    register_notice_type(
        _test_type("test.chore", NoticeCategory.TASK, NoticeSeverity.INFO)
    )
    register_notice_type(
        _test_type("test.log", NoticeCategory.LOG, NoticeSeverity.INFO)
    )
    register_notice_type(
        _test_type(
            "test.nodedupe", NoticeCategory.URGENT, NoticeSeverity.INFO, dedupe=False
        )
    )
