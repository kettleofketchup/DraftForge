"""URL-based label extraction for telemetry context."""

import re
from typing import Any

# Known resource patterns and their label names
# Order matters: more specific patterns should come first
RESOURCE_PATTERNS = [
    # WebSocket singular paths (CRITICAL FIX #7)
    (r"/draft/(\d+)", "draft"),
    (r"/tournament/(\d+)", "tournament"),
    # Plural resources with IDs
    (r"/tournaments/(\d+)", "tournament"),
    (r"/drafts/(\d+)", "draft"),
    (r"/leagues/(\d+)", "league"),
    (r"/organizations/(\d+)", "organization"),
    (r"/matches/(\d+)", "match"),
    (r"/games/(\d+)", "game"),
    (r"/teams/(\d+)", "team"),
    (r"/users/(\d+)", "user"),
    # Plural resources without IDs (list endpoints)
    (r"/tournaments/?$", "tournament"),
    (r"/drafts/?$", "draft"),
    (r"/leagues/?$", "league"),
    (r"/organizations/?$", "organization"),
    (r"/matches/?$", "match"),
    (r"/games/?$", "game"),
    (r"/teams/?$", "team"),
    (r"/users/?", "user"),  # Includes /users/me/
    # Sub-resources (no ID, just label)
    (r"/standings/?$", "standings"),
    (r"/bracket/?$", "bracket"),
    (r"/stats/?$", "stats"),
]


def extract_labels(path: str) -> dict[str, Any]:
    """
    Extract contextual labels from a URL path.

    Parses URL patterns to produce metadata for logging and tracing.
    Uses OTel semantic conventions for field names.

    Args:
        path: URL path (e.g., "/api/tournaments/5/draft/12/")

    Returns:
        Dict with 'labels' list and resource IDs, e.g.:
        {"labels": ["tournament", "draft"], "tournament.id": 5, "draft.id": 12}

        Returns empty dict for unrecognized paths.
    """
    # Process API paths and WebSocket paths
    # WebSocket paths like /ws/draft/5/ or /draft/5/ don't have /api/ prefix
    is_api_path = path.startswith("/api/")
    is_ws_path = (
        path.startswith("/ws/")
        or path.startswith("/draft/")
        or path.startswith("/tournament/")
    )

    if not (is_api_path or is_ws_path):
        return {}

    result: dict[str, Any] = {}

    # Track matches with their position in the URL for proper ordering
    # Format: (position, resource_name, resource_id or None)
    matches: list[tuple[int, str, int | None]] = []
    matched_resources: set[str] = set()

    for pattern, resource_name in RESOURCE_PATTERNS:
        match = re.search(pattern, path)
        if match:
            # Avoid duplicate labels
            if resource_name not in matched_resources:
                matched_resources.add(resource_name)

                # Extract ID if present in capture group
                resource_id = None
                if match.groups():
                    try:
                        resource_id = int(match.group(1))
                    except (ValueError, IndexError):
                        pass

                # Store match with its position in the URL
                matches.append((match.start(), resource_name, resource_id))

    # Sort by position in URL to maintain path order
    matches.sort(key=lambda x: x[0])

    # Build result with labels in URL order
    labels = []
    for _, resource_name, resource_id in matches:
        labels.append(resource_name)
        if resource_id is not None:
            result[f"{resource_name}.id"] = resource_id

    if labels:
        result["labels"] = labels

    return result
