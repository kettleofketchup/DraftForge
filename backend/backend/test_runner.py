from pathlib import Path
from typing import Any

from django.test.runner import DiscoverRunner

BACKEND_DIR: str = str(Path(__file__).resolve().parent.parent)


class BackendDiscoverRunner(DiscoverRunner):
    """Anchor discovery at backend/ so modules import as `app.tests...`.

    backend/ and the repo root both hold an __init__.py, so unittest would
    otherwise walk the top-level directory up past backend/.
    """

    def __init__(self, *args: Any, top_level: str | None = None, **kwargs: Any) -> None:
        super().__init__(*args, top_level=top_level or BACKEND_DIR, **kwargs)
