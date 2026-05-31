"""
Test Database Population Package

This package contains modular functions for populating the test database.
Each module focuses on a specific domain:
- organizations: Organization and league setup
- users: User population (mock and real)
- tournaments: Tournament population
- steam: Steam match data population
- bracket: Bracket-specific test scenarios
- demo: Demo tournaments for video recording

Usage:
    from tests.populate import populate_all
    populate_all(force=True)

Or import specific functions:
    from tests.populate import populate_users, populate_tournaments
"""

from tests.helpers.tournament_config import populate_test_tournaments

# Re-export commonly used functions for backwards compatibility
from tests.populate.bracket import (
    populate_bracket_linking_scenario,
    populate_bracket_unset_winner_tournament,
)

# Re-export constants
from tests.populate.constants import (
    DTX_LEAGUE_NAME,
    DTX_ORG_NAME,
    DTX_STEAM_LEAGUE_ID,
    MOCK_USERNAMES,
    TEST_LEAGUE_NAME,
    TEST_ORG_NAME,
    TEST_STEAM_LEAGUE_ID,
    TOURNAMENT_USERS,
)
from tests.populate.auth_matrix import populate_auth_matrix_data
from tests.populate.csv_import import populate_csv_import_data
from tests.populate.org_delete import populate_org_delete
from tests.populate.demo import populate_demo_tournaments
from tests.populate.events import populate_events_data
from tests.populate.organizations import populate_organizations_and_leagues
from tests.populate.shuffle_tie import populate_shuffle_tie_data
from tests.populate.steam import populate_steam_matches
from tests.populate.tournaments import populate_real_tournament_38, populate_tournaments
from tests.populate.user_edit import populate_user_edit_data
from tests.populate.users import populate_test_auth_users, populate_users

# Re-export utilities that may be used directly
from tests.populate.utils import (
    REAL_TOURNAMENT_USERS,
    create_user,
    ensure_league_user,
    ensure_org_user,
    flush_redis_cache,
    generate_mock_discord_members,
    get_or_create_demo_user,
    test_user_to_dict,
)


def populate_all(force=False):
    """
    Run all population functions in the correct order.

    Args:
        force: If True, recreate data even if it exists
    """
    import io
    import sys
    import time

    from rich.console import Console
    from rich.table import Table

    steps = [
        ("Organizations & Leagues", populate_organizations_and_leagues),
        ("Org Delete Data", populate_org_delete),
        ("Users", populate_users),
        ("Test Auth Users", populate_test_auth_users),
        ("Tournaments", populate_tournaments),
        ("Steam Matches", populate_steam_matches),
        ("Test Tournaments", populate_test_tournaments),
        ("Bracket Linking", populate_bracket_linking_scenario),
        ("Real Tournament 38", populate_real_tournament_38),
        ("Bracket Unset Winner", populate_bracket_unset_winner_tournament),
        ("CSV Import Data", populate_csv_import_data),
        ("User Edit Data", populate_user_edit_data),
        ("Shuffle Tie Data", populate_shuffle_tie_data),
        ("Events Data", populate_events_data),
        # Auth Matrix runs after every other isolated-org populate so its
        # auto-incremented org pk lands on 8 (matching AUTH_MATRIX_ORG.pk).
        ("Auth Matrix Data", populate_auth_matrix_data),
        ("Demo Tournaments", populate_demo_tournaments),
    ]

    console = Console()
    total = len(steps)
    console.print(f"\n[bold]Populating test database ({total} steps)[/bold]\n")

    results = []
    overall_start = time.time()

    for i, (name, fn) in enumerate(steps, 1):
        console.print(f"  [dim][{i}/{total}][/dim] [blue]{name}[/blue]...", end=" ")
        start = time.time()
        # Capture stdout from populate functions to keep output clean
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            fn(force)
        finally:
            sys.stdout = old_stdout
        elapsed = time.time() - start
        console.print(f"[green]{elapsed:.1f}s[/green]")
        results.append((name, elapsed))

    overall = time.time() - overall_start
    console.print(
        f"\n[bold green]All {total} steps completed in {overall:.1f}s[/bold green]\n"
    )


__all__ = [
    # Main entry point
    "populate_all",
    # Population functions
    "populate_organizations_and_leagues",
    "populate_users",
    "populate_test_auth_users",
    "populate_tournaments",
    "populate_real_tournament_38",
    "populate_shuffle_tie_data",
    "populate_steam_matches",
    "populate_bracket_linking_scenario",
    "populate_bracket_unset_winner_tournament",
    "populate_csv_import_data",
    "populate_org_delete",
    "populate_user_edit_data",
    "populate_events_data",
    "populate_auth_matrix_data",
    "populate_demo_tournaments",
    "populate_test_tournaments",
    # Utilities
    "create_user",
    "generate_mock_discord_members",
    "ensure_org_user",
    "ensure_league_user",
    "flush_redis_cache",
    "test_user_to_dict",
    "get_or_create_demo_user",
    "REAL_TOURNAMENT_USERS",
    # Constants
    "DTX_ORG_NAME",
    "DTX_LEAGUE_NAME",
    "DTX_STEAM_LEAGUE_ID",
    "TEST_ORG_NAME",
    "TEST_LEAGUE_NAME",
    "TEST_STEAM_LEAGUE_ID",
    "TOURNAMENT_USERS",
    "MOCK_USERNAMES",
]
