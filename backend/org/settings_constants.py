from django.db import models

ALL_CODES: list[str] = [
    "gate_outside",
    "gate_out_of_range",
    "over_capacity",
    "special_seat_role_mismatch",
    "maybe_special_seat",
    "maybe_forced_main",
]

WARNING_CODE_LABELS: dict[str, str] = {
    "gate_outside": "Outside the signup gate window",
    "gate_out_of_range": "Outside the gate's allowed range",
    "over_capacity": "Roster over capacity",
    "special_seat_role_mismatch": "Special seat given to the wrong role",
    "maybe_special_seat": "'Maybe' member placed in a special seat",
    "maybe_forced_main": "'Maybe' member forced into a main seat",
}


class StaffOverridePolicy(models.TextChoices):
    SILENT = "silent", "Silent"
    CONFIRM = "confirm", "Confirm"
    BLOCK = "block", "Block"


def default_warning_codes() -> list[str]:
    return list(ALL_CODES)
