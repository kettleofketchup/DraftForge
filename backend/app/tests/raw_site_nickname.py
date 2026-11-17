from django.db import connection


def raw_site_nickname(user_id: int) -> str | None:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT nickname FROM user_baseuserprofile WHERE user_id=%s", [user_id]
        )
        row = cursor.fetchone()
    return row[0] if row else None


def set_raw_site_nickname(user_id: int, value: str | None) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE user_baseuserprofile SET nickname=%s WHERE user_id=%s",
            [value, user_id],
        )
