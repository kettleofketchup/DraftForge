from typing import Literal

from rest_framework.exceptions import AuthenticationFailed

ActivityCode = Literal[
    "activity_session_ended",
    "activity_out_of_scope",
    "activity_path_not_allowed",
    "activity_disabled",
]


class ActivityAuthFailed(AuthenticationFailed):
    def __init__(self, activity_code: ActivityCode, detail: str, reason: str) -> None:
        super().__init__(detail)
        self.activity_code: ActivityCode = activity_code
        self.reason: str = reason
