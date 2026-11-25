import ast
import tempfile
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, replace
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.db.migrations.loader import MigrationLoader
from django.test import SimpleTestCase

from config.installed_apps import MODEL_APPS


@dataclass(frozen=True)
class MovedSlice:
    name: str
    source_app: str
    new_app: str
    moved: frozenset[tuple[str, str]]
    retired_modules: frozenset[str]
    model_labels: frozenset[str]
    move_migration: tuple[str, str]
    cached_labels: frozenset[str]


@dataclass(frozen=True)
class BackEdge:
    names: frozenset[str]
    reason: str
    type_only: frozenset[str] = frozenset()


HERO_DRAFT = MovedSlice(
    name="hero-draft",
    source_app="app",
    new_app="draft",
    moved=frozenset(
        {
            ("app.models", "HeroDraftState"),
            ("app.models", "HeroDraft"),
            ("app.models", "DraftTeam"),
            ("app.models", "HeroDraftRound"),
            ("app.models", "HeroDraftEvent"),
            ("app.consumers", "HeroDraftConsumer"),
            ("app.broadcast", "broadcast_herodraft_event"),
            ("app.broadcast", "broadcast_herodraft_state"),
            ("app.draft_state", "herodraft_state_queryset"),
            ("app.serializers", "HeroDraftRoundSerializerFull"),
            ("app.serializers", "DraftTeamSerializerFull"),
            ("app.serializers", "HERODRAFT_GUILD_NICKNAMES"),
            ("app.serializers", "HeroDraftUserSerializer"),
            ("app.serializers", "HeroDraftTeamSerializer"),
            ("app.serializers", "HeroDraftEventSerializer"),
            ("app.serializers", "HeroDraftSerializer"),
            ("app.serializers", "HeroDraftTickSerializer"),
            ("app.serializers_ssr", "HeroDraftSerializerSSR"),
            ("app.views.ssr", "HeroDraftSSRView"),
            ("app.views.internal", "list_auto_herodraft_games"),
            ("app.views.internal", "create_herodraft_for_game"),
            ("app.admin", "HeroDraftEventInline"),
            ("app.admin", "HeroDraftAdmin"),
            ("app.admin", "HeroDraftEventAdmin"),
            ("app.signals", "reset_herodraft_on_team_change"),
            ("app.signals", "_broadcast_draft_event"),
            ("app.consumers", "broadcast_herodraft_state"),
            ("app.consumers", "herodraft_state_queryset"),
            ("app.consumers", "HeroDraftSerializer"),
            ("app.broadcast", "herodraft_state_queryset"),
            ("app.views.internal", "new_herodraft_for_game"),
        }
    ),
    retired_modules=frozenset(
        {
            "app.functions.herodraft",
            "app.functions.herodraft_views",
            "app.tasks.herodraft_tick",
        }
    ),
    model_labels=frozenset(
        {"herodraft", "draftteam", "herodraftround", "herodraftevent"}
    ),
    move_migration=("app", "0108_move_hero_draft_models_to_draft"),
    cached_labels=frozenset({"herodraft", "draftteam"}),
)

TEAM_DRAFT = MovedSlice(
    name="team-draft",
    source_app="app",
    new_app="draft",
    moved=frozenset(
        {
            ("app.models", "TeamDraftState"),
            ("app.models", "TimeoutAction"),
            ("app.models", "Draft"),
            ("app.models", "DraftRound"),
            ("app.models", "DraftEvent"),
            ("app.models", "DraftOptions"),
            ("app.consumers", "DraftConsumer"),
            ("app.consumers", "emit_event"),
            ("app.consumers", "team_payload"),
            ("app.consumers", "build_draft_state"),
            ("app.consumers", "TickDriver"),
            ("app.consumers", "TEAM_TICK_DRIVER"),
            ("app.consumers", "captain_conn_key"),
            ("app.consumers", "captain_is_fresh"),
            ("app.consumers", "DraftEventSerializer"),
            ("app.serializers", "DraftSerializer"),
            ("app.serializers", "TournamentSerializerDraft"),
            ("app.serializers", "DraftSerializerMMRs"),
            ("app.serializers", "DraftRoundSerializer"),
            ("app.serializers", "DraftEventSerializer"),
            ("app.views_main", "DraftView"),
            ("app.views_main", "DraftRoundView"),
            ("app.views_main", "DraftCreateView"),
            ("app.views_main", "DraftRoundCreateView"),
            ("app.views", "DraftView"),
            ("app.views", "DraftRoundView"),
            ("app.views", "DraftCreateView"),
            ("app.views", "DraftRoundCreateView"),
            ("app.permissions_org", "CanEditDraft"),
            ("app.permissions_org", "CanEditDraftRound"),
            ("app.permissions_tournament", "CanEditDraft"),
            ("app.permissions_tournament", "CanEditDraftRound"),
            ("app.functions.tournament", "generate_draft_rounds"),
            ("app.functions.tournament", "rebuild_team"),
            ("app.functions.tournament", "get_draft_style_mmrs"),
            ("app.functions.tournament", "CreateDraftRounds"),
            ("app.functions.tournament", "DraftPredictMMRSerializer"),
            ("app.functions.tournament", "_get_or_create_draft"),
            ("app.functions.tournament", "_notify_draft_started_after_commit"),
            ("app.functions.tournament", "reset_draft_teams"),
            ("app.functions.tournament", "NoEligibleCaptains"),
            ("app.functions.tournament", "TeamsReferenced"),
            ("app.functions.tournament", "DraftSerializerMMRs"),
            ("app.functions.tournament", "notify_draft_started"),
        }
    ),
    retired_modules=frozenset(
        {
            "app.functions.teamdraft",
            "app.functions.teamdraft_timeout",
            "app.functions.teamdraft_views",
            "app.functions.shuffle_draft",
            "app.functions.draft_picks",
            "app.tasks.draft_tick",
            "app.tasks.teamdraft_tick",
            "app.broadcast",
            "app.draft_state",
            "app.consumers_base",
            "app.services.draft_reset",
            "app.tests.teamdraft_fixtures",
            "app.tests.ws_helpers",
        }
    ),
    model_labels=frozenset({"draft", "draftround", "draftevent", "draftoptions"}),
    move_migration=("app", "0109_move_team_draft_models_to_draft"),
    cached_labels=frozenset({"draft", "draftoptions", "draftround"}),
)

_ORG_PERMISSION_NAMES = (
    "is_org_owner",
    "has_org_admin_access",
    "has_org_staff_access",
    "is_org_role_holder",
    "has_org_promoter_access",
    "can_view_org_members",
    "_payload_lists_user",
    "_payload_has_user",
    "org_admin_staff_from_payload",
    "can_view_org_members_from_payload",
    "IsOrgOwner",
    "IsOrgAdmin",
    "IsOrgStaff",
)

_ORG_ADMIN_TEAM_VIEWS = (
    "add_org_admin",
    "remove_org_admin",
    "add_org_staff",
    "remove_org_staff",
    "transfer_org_ownership",
    "add_org_member",
    "update_org_user",
    "_find_member",
    "_cached_guild_member",
    "_member_nick",
    "_resolve_user",
)

ORG = MovedSlice(
    name="org",
    source_app="app",
    new_app="org",
    moved=frozenset(
        {
            ("app.views_main", "OrganizationView"),
            ("app.views_main", "_feature_access"),
            ("app.views_main", "_org_viewer_access"),
            ("app.views_main", "_member_access"),
            ("app.serializers", "OrganizationSerializer"),
            ("app.serializers", "_known_timezones"),
            ("app.serializers_ssr", "OrganizationSerializerSSR"),
            ("app.views.ssr", "OrganizationSSRView"),
            *(
                (module, name)
                for module in ("app.views.admin_team", "app.views.user_search")
                for name in _ORG_ADMIN_TEAM_VIEWS
            ),
            ("app.signals", "track_org_discord_server_id"),
            ("app.signals", "reset_guild_nicknames_on_server_change"),
            ("app.models", "Organization"),
            ("app.models", "OrgLog"),
            *(
                (module, name)
                for module in ("app.permissions_org", "app.permissions_tournament")
                for name in _ORG_PERMISSION_NAMES
            ),
        }
    ),
    retired_modules=frozenset(
        {
            "app.permissions_org",
            "app.tests.test_organization",
            "app.tests.test_org_role_fields",
        }
    ),
    model_labels=frozenset({"organization", "orglog"}),
    move_migration=("app", "0111_move_organization_models_to_org"),
    cached_labels=frozenset({"organization"}),
)

_LEAGUE_PERMISSION_NAMES = (
    "has_league_admin_access",
    "has_league_staff_access",
    "_is_league_member",
    "can_view_league_members",
    "can_view_league_members_from_payload",
    "IsLeagueAdmin",
    "IsLeagueStaff",
)

_LEAGUE_ADMIN_TEAM_VIEWS = (
    "add_league_admin",
    "remove_league_admin",
    "add_league_staff",
    "remove_league_staff",
    "add_league_member",
)

_LEAGUE_RETIRED_TEST_DEFS = {
    "app.tests.test_league": ("LeagueAPITest",),
    "app.tests.test_league_role_fields": ("LeagueRoleFieldsTest",),
    "app.tests.test_league_serializer": (
        "LeaguePatchSteamLeagueIdCacheTest",
        "LeaguePatchSteamLeagueIdTest",
        "LeagueUsersNameFieldsTest",
        "ValidateSteamLeagueIdTest",
    ),
    "app.tests.test_match_finalization": (
        "AgeDecayCalculationTest",
        "MatchFinalizationServiceTest",
    ),
}

LEAGUE = MovedSlice(
    name="league",
    source_app="app",
    new_app="league",
    moved=frozenset(
        {
            ("app.views_main", "LeagueView"),
            ("app.serializers", "LeagueSerializer"),
            ("app.serializers_ssr", "LeagueSerializerSSR"),
            ("app.views.ssr", "LeagueSSRView"),
            ("app.services", "LeagueMatchService"),
            ("app.services", "get_rating_system"),
            ("app.services", "EloRatingSystem"),
            ("app.services", "FixedDeltaRatingSystem"),
            ("app.services.rating", "RatingSystem"),
            ("app.services.rating", "EloRatingSystem"),
            ("app.services.rating", "FixedDeltaRatingSystem"),
            ("app.services.rating", "get_rating_system"),
            ("app.services.match_finalization", "LeagueMatchService"),
            ("app.models", "League"),
            ("app.models", "LeagueRating"),
            ("app.models", "LeagueMatch"),
            ("app.models", "LeagueMatchParticipant"),
            ("app.models", "LeagueLog"),
            *(
                (module, name)
                for module in ("app.views.admin_team", "app.views.user_search")
                for name in _LEAGUE_ADMIN_TEAM_VIEWS
            ),
            *(
                ("app.permissions_tournament", name)
                for name in _LEAGUE_PERMISSION_NAMES
            ),
            *(
                (module, name)
                for module, names in _LEAGUE_RETIRED_TEST_DEFS.items()
                for name in names
            ),
        }
    ),
    retired_modules=frozenset(
        {
            "app.services.rating",
            "app.services.match_finalization",
            "app.tests.test_league",
            "app.tests.test_league_role_fields",
            "app.tests.test_league_serializer",
            "app.tests.test_match_finalization",
            "app.tests.test_league_rating",
        }
    ),
    model_labels=frozenset(
        {"league", "leaguerating", "leaguematch", "leaguematchparticipant", "leaguelog"}
    ),
    move_migration=("app", "0112_move_league_models_to_league"),
    cached_labels=frozenset({"league"}),
)

_TOURNAMENT_PERMISSION_NAMES = (
    "can_edit_tournament",
    "can_create_team",
    "_league_change_error",
    "check_tournament_league_change",
    "can_manage_game",
    "CanEditTournament",
    "CanEditTeam",
    "CanManageGame",
    "IsTournamentStaff",
    "has_event_staff_access",
    "check_lobby_steam_league_id",
    "_lobby_league_error",
)

_TOURNAMENT_CLIENT_NAMES = (
    "create_herodraft_for_game",
    "get_auto_herodraft_games",
    "get_match_participants",
    "get_tournament_for_task",
    "get_tournament_participants",
)

_TOURNAMENT_SCHEMA_NAMES = (
    "TournamentParticipantSchema",
    "TournamentTaskSchema",
    "GameWithoutHeroDraftSchema",
    "AutoHeroDraftGameSchema",
)

_TOURNAMENT_SERIALIZER_NAMES = (
    "tournament_organization",
    "_serialize_users_with_mmr",
    "serialize_user_with_mmr",
    "TEAM_USER_INDEX",
    "TEAM_MMR_MAPS",
    "TEAM_ROSTER_FIELDS",
    "TeamUserIndex",
    "build_team_user_index",
    "collect_tournament_user_pks",
    "_CONTEXT_MMR_KEYS",
    "collect_org_mmr",
    "build_users_dict",
    "build_users_dict_with_org",
    "TournamentSerializerBase",
    "TeamSerializerForTournament",
    "TeamSerializerSlim",
    "TeamSerializer",
    "team_mmr_user_ids",
    "build_team_mmr_maps",
    "_leadership_problem_rows",
    "ManagedTeamSerializer",
    "TournamentTeamSerializer",
    "TeamLogSerializer",
    "TeamActionRequestSerializer",
    "TeamUserActionRequestSerializer",
    "TeamDeputyRequestSerializer",
    "TeamSubInRequestSerializer",
    "TeamRenameRequestSerializer",
    "users_remaining_pks",
    "_shared_draft_options",
    "_prefetched_draft_options",
    "DraftRoundForDraftSerializer",
    "DraftRoundSerializerSlim",
    "TournamentSerializerForWebSocket",
    "DraftOptionsSerializer",
    "DraftSerializerForTournament",
    "DraftSerializerSlim",
    "GameSerializerForTournament",
    "GameSerializer",
    "BracketGameSerializer",
    "BracketSaveSerializer",
    "BracketGenerateSerializer",
    "LeagueMatchSerializer",
    "TournamentsSerializer",
    "TournamentListSerializer",
    "TournamentSerializer",
    # org/league serializers that moved to org.serializers and league.serializers
    "OrganizationsSerializer",
    "LeaguesSerializer",
    "LeagueMinimalSerializer",
)

# names split out of app modules that stay behind
_TOURNAMENT_SPLIT_DEFS = {
    "app.management.prod_payload": (
        "TeamLookup",
        "TeamRef",
        "UserRef",
        "index_users",
        "parse_date_played",
        "resolve_user",
    ),
    "app.tests.test_prod_import_commands": (
        "ImportProdTournamentCommandTest",
        "SyncProdTournamentsCommandTest",
        "mmr_rows",
        "tournament_payload",
    ),
    "app.tests.test_import_order": ("TOURNAMENT_SERIALIZER_MODULES",),
    "app.tests.test_internal_endpoints": ("TournamentParticipantsEndpointTest",),
    "app.tests.test_schema_drift": (
        "GameWithoutHeroDraftSchemaDriftTest",
        "TournamentParticipantSchemaDriftTest",
        "TournamentTaskSchemaDriftTest",
    ),
}

_TOURNAMENT_RETIRED_DEFS = {
    "app.services.team_management": (
        "TeamChange",
        "TeamManagementError",
        "_apply",
        "_change_captain",
        "_dropout_mutation",
        "_ensure_tournament_user",
        "_is_dropout",
        "_is_member",
        "_is_standin",
        "_captain_source",
        "_eligibility_violations",
        "_leadership_touched_by",
        "_live_after_reopen",
        "_live_other_teams",
        "_on_other_team_error",
        "_org_settings",
        "_problem_pairs",
        "_refresh_herodrafts",
        "_standin_violations",
        "add_standin",
        "follow_captain",
        "live_conflicts",
        "mark_dropout",
        "other_team_user_ids",
        "remove_standin",
        "rename",
        "replace_captain",
        "restore_member",
        "roster_conflict_body",
        "set_captain",
        "set_deputy",
        "standin_cap",
        "sub_in",
        "broadcast_herodraft_state",
    ),
    "app.services.team_references": (
        "TeamRef",
        "TeamUsage",
        "_key",
        "_reference_relations",
        "_team_rows",
        "_usage_sort_key",
        "all_reference_keys",
        "team_references",
        "team_usage",
    ),
    "app.services.team_audit": (
        "_sorted_ids",
        "log_snapshot_fields",
        "roster_snapshot",
        "source_event",
        "write_team_log",
    ),
    "app.services.team_signals": (
        "TeamRosterChange",
        "_receiver_name",
        "change_from_log",
        "owning_team_audit",
        "send_roster_changed_on_commit",
        "team_roster_changed",
        "team_audit_owner",
    ),
    "app.services.team_leadership": (
        "successor_after_removal",
        "teams_with_leadership_problems",
    ),
    "app.services.tournament_completion": (
        "find_final_game",
        "sync_tournament_completion",
    ),
    "app.signals": (
        "_after_members_removed",
        "_before_removal",
        "_handle_empty_team",
        "_handle_reverse_member_change",
        "_write_system_log",
        "handle_team_member_removal",
        "handle_tournament_user_addition",
        "handle_tournament_user_removal",
        "sync_tournament_on_game_result",
        "track_game_winner_change",
        "team_roster_changed",
    ),
    "app.management.commands.audit_team_leadership": ("Command",),
    "app.management.commands.import_prod_tournament": ("Command", "requests"),
    "app.management.commands.sync_prod_tournaments": ("Command", "requests"),
    "app.tests.test_team_management": (
        "AddStandinTests",
        "CaptainDraftFollowUpTests",
        "DraftBookkeepingTests",
        "DropoutTests",
        "EliminatedTeamRuleTests",
        "FixtureHelperTests",
        "HeroDraftCaptainCacheTests",
        "InvariantTests",
        "RenameTests",
        "ReplaceCaptainTests",
        "ReseatGhostDeputyTests",
        "RosterSignalTests",
        "SetCaptainTests",
        "SetDeputyTests",
        "StandinAndRestoreTests",
        "SubInTests",
        "SubInTournamentUserTests",
        "TeamManagementCacheTests",
        "TeamManagementFixture",
        "TournamentCacheTests",
        "_problems",
        "eliminate",
    ),
    "app.tests.test_team_signals": (
        "EmptyTeamAuditTests",
        "KnockedOutRosterCascadeTests",
        "SuccessionAuditTests",
        "SuccessorAfterRemovalTests",
        "SystemRowSignalTests",
        "TeamMemberRemovalTests",
        "TeamValidationTests",
        "TournamentUserRemovalCascadeTests",
        "_roster_user",
    ),
    "app.tests.test_team_roster_signal": ("TeamRosterSignalTests",),
    "app.tests.test_team_references": (
        "TeamReferencesFixture",
        "TeamReferencesTests",
        "TeamUsageTests",
    ),
    "app.tests.test_tournament_completion": (
        "AdvanceWinnerCompletionTest",
        "BracketShapeCompletionTest",
        "SaveBracketCompletionTest",
        "SteamLinkCompletionTest",
        "TournamentCompletionTestBase",
    ),
    "app.tournament_state": (
        "draft_round_prefetch",
        "qs",
        "team_prefetches",
        "tournament_prefetches",
        "tournament_state_queryset",
    ),
    "app.tournament_list": (
        "ArchiveCursor",
        "TournamentListPagination",
        "TournamentListParams",
        "_parse_cursor",
        "_parse_int",
        "_parse_open_signups",
        "_parse_organizations",
        "archive_after_q",
        "build_cursor_envelope",
        "build_page_envelope",
        "decode_archive_cursor",
        "normalize_search",
        "parse_tournament_list_params",
        "resolve_organizations",
        "tournaments_list_cache_key",
        "TOURNAMENTS_LIST_CACHE_PREFIX",
    ),
    "app.tournament_buckets": (
        "_now",
        "tournament_bucket_cutoff",
        "upcoming_q",
        "upcoming_rank",
        "utc_day_start",
    ),
    "app.functions.tournament": (
        "CreateTournamentTeamRequestSerializer",
        "create_team_from_captain",
        "serialize_tournament",
    ),
    "app.internal_client.tournaments": _TOURNAMENT_CLIENT_NAMES,
    "app.tests.test_tournament_list": (
        "LeagueMinimalSerializerTests",
        "TournamentListArchivedCursorTests",
        "TournamentListBucketTests",
        "TournamentListPaginationTests",
        "_BucketFixtureMixin",
    ),
    "app.tests.test_tournament_buckets": (
        "ArchiveCursorTests",
        "BuildPageEnvelopeTests",
        "NormalizeSearchTests",
        "ParseTournamentListParamsTests",
        "ResolveOrganizationsTests",
        "TournamentBucketCutoffTests",
        "TournamentListPaginationTests",
        "TournamentsListCacheKeyTests",
        "_b64",
    ),
    "app.tests.test_tournament_state_queries": (
        "TournamentResponseFreshTests",
        "TournamentResponseOutputTests",
        "TournamentResponseQueryCountTests",
    ),
    "app.tests.test_tournament_discovery_seed": ("TournamentDiscoverySeedTests",),
    "app.tests.test_tournament_list_cache": ("TournamentListCacheTests",),
    "app.tests.test_tournament_list_scope": ("TournamentListScopeTests",),
    "app.tests.test_build_users_dict": (
        "BuildUsersDictOrgTests",
        "BuildUsersDictNonOrgTests",
        "BuildUsersDictLeaguelessEventTests",
        "ORG_ENTRY_KEYS",
        "NONORG_ENTRY_KEYS",
    ),
    "app.tests.test_tournament_serializer": (
        "TournamentSourceEventSerializerTest",
        "TournamentLobbyConfigFieldsTest",
    ),
    "app.tests.test_team_serializer": (
        "_user",
        "TeamLeadershipApiTests",
        "TeamLeadershipMessagesTests",
        "TeamLeadershipAuditTests",
        "TeamLegacyPatchTests",
        "_discord_ids",
    ),
    "app.views.bracket": (
        "get_bracket",
        "generate_bracket",
        "save_bracket",
        "calculate_placement",
        "_unset_winner",
        "advance_winner",
        "set_team_placement",
        "_foreign_team_ids",
    ),
    "app.views.csv_import": (
        "_parse_int",
        "_parse_positions",
        "_update_positions_if_empty",
        "_resolve_user_for_csv_row",
        "import_csv_org",
        "_parse_mmr_cell",
        "_flush_org_mmrs",
        "_update_mmr_for_target",
        "_resync_league_snapshots",
        "import_csv_tournament",
        "bulk_set_org_mmrs",
    ),
    "app.tests.test_bracket": (
        "SaveBracketTest",
        "CalculatePlacementTest",
        "AdvanceWinnerPlacementTest",
        "ManualPlacementOverrideTest",
        "UnsetWinnerTest",
        "AdvanceWinnerPersistenceTest",
        "RosterGuardHelpers",
        "PlacementClearGuardTests",
        "SingleEliminationGuardBracket",
        "PlacementRequestGuardTests",
        "PlacementApplyGuardTests",
        "SingleEliminationFinalUnsetTests",
    ),
    "app.tests.test_bracket_queries": (
        "_user_ids",
        "BracketFixture",
        "build_bracket",
        "per_team_serialization",
        "BracketQueryTests",
    ),
    "app.tests.test_csv_import": (
        "OrgCSVImportTest",
        "OrgCSVImportDotaRowTest",
        "OrgCSVImportGameTypeFixtures",
        "OrgCSVImportGameTypeTest",
        "OrgCSVImportCacheTest",
    ),
    "app.tests.test_csv_import_tournament": (
        "TournamentCSVImportTest",
        "TournamentCSVImportDotaRowTest",
        "TournamentCSVImportGameTest",
    ),
    "app.tests.test_tournament_edit_config": (
        "TournamentEditConfigBase",
        "TournamentEditConfigTests",
        "TournamentLobbySteamLeagueIdTests",
        "TournamentDiscordLogsAccessTests",
    ),
    "app.tests.test_tournament_detail_cache": ("TournamentDetailStaleWriteTests",),
    "app.tests.test_tournament_league_move": ("TournamentLeagueMoveTests",),
    "app.tests.test_game_org_mmr_drafts": (
        "_make_user",
        "CaptainSuccessionRegressionTests",
        "GameOrgMmrFixtures",
        "GameOrgMmrDraftTests",
        "GameOrgMmrSuccessionTests",
        "GameOrgMmrEdgeTests",
        "DraftStyleMmrsCacheTests",
    ),
    "app.tests.test_game_org_mmr_league": (
        "_discord_seq",
        "_make_user",
        "_rating_selects",
        "_capture",
        "LeagueFixtures",
        "LeagueSnapshotTests",
        "MatchFinalizationGameMmrTests",
        "UpdateUserLeagueMmrTests",
        "OrgUserCreationSitesTests",
    ),
    "app.tests.test_game_org_mmr_payloads": (
        "_discord_ids",
        "_make_user",
        "NumericDiscordFixtures",
        "_map_queries",
        "_count",
        "OrgUsersEndpointTests",
        "OrgUserSerializerContextTests",
        "PublicPayloadGameTests",
        "TeamTotalsQueryTests",
        "UserSerializerTeamsTests",
        "ClaimRequestPayloadTests",
        "OrgUserPatchResponseTests",
        "DeadlockFreshReadTests",
    ),
    "app.tests.test_team_management_api": (
        "TeamActionRequestSerializerTests",
        "_dumps",
        "_count_queries",
        "ResponseSerializerTests",
        "TournamentLeadershipQueryTests",
        "ExceptionHandlerTests",
        "action_url",
        "ActionCase",
        "prepare_restore",
        "prepare_standins_remove",
        "prepare_sub_in",
        "prepare_replace_captain",
        "TeamApiFixture",
        "TeamActionPermissionTests",
        "LeadershipActionTests",
        "RosterActionTests",
        "CachedPermissionTests",
        "CanManageTeamTests",
        "CanManageTeamCacheTests",
        "TeamHistoryTests",
        "LegacyDeleteTests",
        "TeamUsageTests",
        "ReplaceCaptainApiTests",
        "TeamPatchPlacementGuardTests",
    ),
    "app.tests.test_team_create_permissions": ("TeamCreatePermissionTests",),
    "app.tests.test_tournament_viewer": (
        "TournamentViewerTests",
        "LeaguelessEventTournamentViewerTests",
    ),
    "app.tests.test_team_name_from_captain": ("TeamNameFromCaptainTest",),
    "app.views.admin_team": ("add_tournament_member",),
    "app.consumers": ("TournamentConsumer",),
    "app.routing": ("websocket_urlpatterns",),
    "app.tests.test_add_member": (
        "AddLeagueMemberTest",
        "AddTournamentMemberTest",
        "_discord_member",
        "AddMemberGuildNicknameTest",
    ),
    "app.tests.test_team_log": ("TeamLogModelTests",),
    "app.tests.test_tournament_migration": ("TournamentFieldsTests",),
}

_TOURNAMENT_VIEW_NAMES = (
    "TournamentView",
    "TournamentsBasicView",
    "TournamentListView",
    "TournamentCreateView",
    "TEAM_MANAGE_ACTIONS",
    "TeamServiceCall",
    "TeamLogPagination",
    "_can_read_scope",
    "_scope_q",
    "_team_in_use_detail",
    "TeamView",
    "_check_can_create_team",
    "TeamCreateView",
    "GameCreateView",
    "GameView",
)

_TOURNAMENT_MODEL_NAMES = (
    "Tournament",
    "Team",
    "Game",
    "TeamLog",
    "LeadershipProblem",
    "_LEADERSHIP_MESSAGES",
    "TeamLogVia",
    "TeamLogAction",
    "DraftStyles",
    "GameMode",
    "DotaLobbyMode",
    "DotaLobbyLaunch",
    "TOURNAMNET_TYPE_CHOICES",
)

TOURNAMENT = MovedSlice(
    name="tournament",
    source_app="app",
    new_app="tournament",
    moved=frozenset(
        {
            *(
                ("app.permissions_tournament", name)
                for name in _TOURNAMENT_PERMISSION_NAMES
            ),
            *(
                (module, name)
                for module, names in _TOURNAMENT_RETIRED_DEFS.items()
                for name in names
            ),
            *(("app.internal_client", name) for name in _TOURNAMENT_CLIENT_NAMES),
            *(("app.schemas", name) for name in _TOURNAMENT_SCHEMA_NAMES),
            *(("app.serializers", name) for name in _TOURNAMENT_SERIALIZER_NAMES),
            *(("app.views_main", name) for name in _TOURNAMENT_VIEW_NAMES),
            ("app.views.internal", "get_tournament_for_task"),
            ("app.views.internal", "get_tournament_participants"),
            ("app.views.internal", "get_match_participants"),
            ("app.views.ssr", "TournamentSSRView"),
            ("app.serializers_ssr", "TournamentSerializerSSR"),
            ("app.admin", "TeamLogAdmin"),
            *(("app.models", name) for name in _TOURNAMENT_MODEL_NAMES),
            # patched on views_main before the views moved
            ("app.views_main", "build_users_dict"),
            ("app.views_main", "tournament_bucket_cutoff"),
            *(
                ("app.views", name)
                for name in (
                    *_TOURNAMENT_VIEW_NAMES,
                    *_TOURNAMENT_RETIRED_DEFS["app.views.bracket"],
                )
            ),
            *(
                (module, name)
                for module, names in _TOURNAMENT_SPLIT_DEFS.items()
                for name in names
            ),
        }
    ),
    retired_modules=frozenset(
        {"app.permissions_tournament", *_TOURNAMENT_RETIRED_DEFS}
    ),
    model_labels=frozenset({"tournament", "team", "game", "teamlog"}),
    move_migration=("app", "0115_move_tournament_models_to_tournament"),
    cached_labels=frozenset({"tournament", "team", "game"}),
)

_USER_SPLIT_DEFS = {
    "app.views_main": (
        "UserView",
        "UserCreateView",
        "current_user",
        "bulk_users",
        "steam_account_id_lookup",
        "_admin_friend_id_refusal",
        "refresh_avatar",
        "refresh_user_avatar_admin",
        "refresh_all_avatars",
    ),
    "app.functions.user": (
        "ProfileUpdateSerializer",
        "profile_update",
        "_friend_id_error",
    ),
    "app.views.user_search": ("search_users",),
    "app.views.steam_verification": (
        "_load",
        "_payload",
        "_current_id",
        "steam_verification",
    ),
    "app.serializers_ssr": ("UserSerializerSSR",),
    "app.views.ssr": ("UserSSRView",),
    "app.views.internal": ("list_users_for_avatar_check", "update_user_avatar"),
    "app.tests.test_search_users": ("SearchUsersTest",),
    "app.tests.test_user_delete_route": ("UserDeleteRouteTests",),
    "app.tests.test_current_user_membership": ("MemberOrganizationIdsTests",),
    "app.tests.test_user_partial_patch": ("PartialUserPatchTests",),
    "app.tests.test_user_mmr_verification": ("CustomUserMMRVerificationTest",),
    "app.tests.test_user_privilege_fields": ("UserPrivilegeFieldsTests",),
    "app.tests.test_steam_account_id_conflict": (
        "SteamAccountIdConflictTests",
        "SteamAccountIdLookupTests",
        "SteamAccountIdConflictLabelTests",
        "_org_user_url",
        "_reload",
        "OrgUserPatchVerificationTests",
        "UserPatchVerificationTests",
        "AdminLookupBudgetTest",
    ),
    "app.tests.test_views_main_auth": ("RefreshAllAvatarsRateLimitTest",),
    "app.tests.test_internal_avatar_and_sweep": (
        "ListDiscordLinkedUsersTest",
        "ListDiscordGuildIdsTest",
        "BulkUpdateUserAvatarsTest",
    ),
    "app.tests.test_ssr_views": ("SSREndpointTests",),
}

USER = MovedSlice(
    name="user",
    source_app="app",
    new_app="user",
    moved=frozenset(
        {
            *(
                (module, name)
                for module, names in _USER_SPLIT_DEFS.items()
                for name in names
            ),
            ("app.serializers", "UserPkField"),
            ("app.serializers", "PositionsSerializer"),
            ("app.serializers", "TournamentUserSerializer"),
            ("app.serializers", "UserSerializer"),
            ("app.schemas", "TournamentUserSchema"),
            ("app.user_cache", "serialize_user_core"),
            ("app.user_cache", "serialize_users_core"),
            ("app.tests.test_user_core_cache", "SerializeUserCoreTests"),
            ("app.tests.test_user_core_cache", "BulkUsersCacheTests"),
            (
                "app.tests.test_tournament_user_schema",
                "TournamentUserSchemaDisplayNameTest",
            ),
            (
                "app.tests.test_user_serializer_discord_names",
                "UserSerializerDiscordNamesTest",
            ),
            (
                "app.tests.test_user_serializer_discord_names",
                "NoSerializerEmitsCustomUserGuildNicknameTest",
            ),
            ("app.tests.test_user_serializer_discord_names", "_serializer_sources"),
            ("app.tests.test_user_serializer_discord_names", "_in_customuser_meta"),
            ("app.tests.test_user_serializer_payload", "UserSerializerPayloadTest"),
            ("app.tests.test_schema_reexports", "AppSchemaReexportTests"),
            ("app.tasks.avatar_refresh", "_is_test_environment"),
            ("app.tasks.avatar_refresh", "_is_avatar_url_valid"),
            ("app.tasks.avatar_refresh", "_fetch_discord_avatar"),
            ("app.tasks.avatar_refresh", "_check_and_update_user"),
            ("app.tasks.avatar_refresh", "refresh_discord_avatars"),
            ("app.tasks.avatar_refresh", "refresh_single_user_avatar"),
            ("app.tasks.avatar_refresh", "refresh_avatars_batched"),
            ("app.tasks.avatar_refresh", "refresh_all_discord_data"),
            ("app.tasks.discord_name_sync", "_sync_targets"),
            ("app.tasks.discord_name_sync", "sync_active_org_discord_names"),
            ("app.tasks.discord_name_sync", "sync_org_discord_names"),
            ("app.internal_client.users", "get_users_for_avatar_check"),
            ("app.internal_client.users", "update_user_avatar"),
            ("app.internal_client.users", "list_discord_linked_users"),
            ("app.internal_client.users", "list_discord_guild_ids"),
            ("app.internal_client.users", "bulk_update_user_avatars"),
            ("app.internal_client.users", "list_discord_name_sync_targets"),
            ("app.internal_client.users", "bulk_update_member_names"),
            ("app.utils.avatar_utils", "refresh_user_avatar"),
            ("app.management.prod_payload", "steam_account_id"),
            ("app.management.prod_payload", "position_values"),
            ("app.management.prod_payload", "create_positions"),
            ("app.management.commands.refresh_avatars", "Command"),
            ("app.management.commands.sync_prod_users", "Command"),
            ("app.tests.test_avatar_refresh_batched", "_user_row"),
            ("app.tests.test_avatar_refresh_batched", "AvatarRefreshBatchedTest"),
            ("app.tests.test_discord_name_sync_task", "_member"),
            ("app.tests.test_discord_name_sync_task", "DiscordNameSyncTaskTests"),
            ("app.tests.test_discord_name_sync_beat", "DiscordNameSyncBeatTests"),
            ("app.tests.test_prod_import_commands", "fake_response"),
            ("app.tests.test_prod_import_commands", "prod_user"),
            ("app.tests.test_prod_import_commands", "SyncProdUsersCommandTest"),
            ("app.internal_client", "bulk_update_member_names"),
            ("app.internal_client", "bulk_update_user_avatars"),
            ("app.internal_client", "get_users_for_avatar_check"),
            ("app.internal_client", "list_discord_guild_ids"),
            ("app.internal_client", "list_discord_linked_users"),
            ("app.internal_client", "list_discord_name_sync_targets"),
            ("app.internal_client", "update_user_avatar"),
            ("app.display_names", "first_name"),
            ("app.display_names", "user_display_name"),
            ("app.steam_accounts", "steam_account_id_holder"),
            ("app.steam_accounts", "steam_account_id_identity"),
            ("app.steam_accounts", "steam_account_id_conflict_payload"),
            ("app.steam_accounts", "_require_id"),
            ("app.steam_accounts", "_apply_verification"),
            ("app.steam_accounts", "log_steam_verification_change"),
            ("app.steam_accounts", "mark_steam_account_verified"),
            ("app.steam_accounts", "clear_steam_account_verification"),
            ("app.steam_accounts", "steam_verification_payload"),
            ("app.discord_accounts", "_GameProfileSnapshot"),
            ("app.discord_accounts", "_positions_set"),
            ("app.discord_accounts", "_snapshot_game_profiles"),
            ("app.discord_accounts", "_carry_over_game_profiles"),
            ("app.discord_accounts", "merge_discord_accounts"),
            ("app.discord_accounts", "find_split_discord_accounts"),
            ("app.pipelines", "save_discord"),
            ("app.pipelines", "associate_by_discord_id"),
            ("app.pipelines", "associate_by_discord_username"),
            ("app.management.commands.reclaim_discord_accounts", "Command"),
            ("app.models", "PositionsModel"),
            ("app.models", "ProfileClaimRequest"),
            ("app.tests.test_discord_pipeline_names", "_social"),
            ("app.tests.test_discord_pipeline_names", "SaveDiscordGlobalNameTest"),
            ("app.tests.test_discord_reclaim", "_social"),
            ("app.tests.test_discord_reclaim", "AssociateByDiscordIdTest"),
            ("app.tests.test_discord_reclaim", "MergeDiscordAccountsTest"),
            ("app.tests.test_discord_reclaim", "_discarded"),
            ("app.tests.test_discord_reclaim", "MergeDiscardedRowsTest"),
            ("app.tests.test_discord_reclaim", "MergeOrgMemberDependentsTest"),
            ("app.tests.test_discord_reclaim", "MergeProfileCarryoverCoverageTest"),
            ("app.tests.test_discord_reclaim", "MergeWithoutBaseProfileTest"),
            ("app.tests.test_discord_reclaim", "GetOrgUserPhantomGuardTest"),
            ("app.tests.test_discord_reclaim", "SaveDiscordCollisionTest"),
            ("app.tests.test_display_names", "FirstNameTest"),
            ("app.tests.test_display_names", "UserDisplayNameTest"),
            ("org.permissions", "is_site_admin"),
            ("app.permissions_org", "is_site_admin"),
        }
    ),
    retired_modules=frozenset(
        {
            "app.functions.user",
            "app.views.user_search",
            "app.views.steam_verification",
            "app.functions",
            "app.tests.test_search_users",
            "app.tests.test_user_delete_route",
            "app.tests.test_current_user_membership",
            "app.tests.test_user_partial_patch",
            "app.tests.test_user_mmr_verification",
            "app.tests.test_user_privilege_fields",
            "app.tests.test_steam_account_id_conflict",
            "app.schemas",
            "app.user_cache",
            "app.tests.test_user_core_cache",
            "app.tests.test_tournament_user_schema",
            "app.tests.test_user_serializer_discord_names",
            "app.tests.test_user_serializer_payload",
            "app.tests.test_schema_reexports",
            "app.tasks",
            "app.tasks.avatar_refresh",
            "app.tasks.discord_name_sync",
            "app.internal_client.users",
            "app.utils.avatar_utils",
            "app.management.prod_payload",
            "app.management.commands.refresh_avatars",
            "app.management.commands.sync_prod_users",
            "app.tests.test_avatar_refresh_batched",
            "app.tests.test_discord_name_sync_task",
            "app.tests.test_discord_name_sync_beat",
            "app.tests.test_prod_import_commands",
            "app.utils",
            "app.steam_accounts",
            "app.pipelines",
            "app.tests.test_discord_pipeline_names",
            "app.tests.test_discord_reclaim",
            "app.tests.test_display_names",
            "app.display_names",
            "app.discord_accounts",
            "app.management.commands.reclaim_discord_accounts",
        }
    ),
    model_labels=frozenset({"positionsmodel", "profileclaimrequest"}),
    move_migration=("app", "0117_move_user_models_to_user"),
    cached_labels=frozenset(),
)

MOVED_SLICES: tuple[MovedSlice, ...] = (
    HERO_DRAFT,
    TEAM_DRAFT,
    ORG,
    LEAGUE,
    TOURNAMENT,
    USER,
)

# Slices cut before the rule that a retired module's defs go into `moved`;
# their modules were renamed or split on the way out.
RETIRED_DEFS_GRANDFATHERED: frozenset[str] = frozenset(
    {HERO_DRAFT.name, TEAM_DRAFT.name, ORG.name}
)

# retired module -> where its defs live now, when that is not the same path
# under the new app; None: no single home file to check (renamed within the
# source app, or a retired package).
RETIRED_MODULE_HOMES: dict[str, str | None] = {
    "app.functions.user": "user.views_profile",
    "app.views.user_search": "user.views_search",
    "app.views.steam_verification": "user.views_steam_verification",
    "app.functions": None,
    "app.tests.test_search_users": "user.tests.test_search_users",
    "app.tests.test_user_delete_route": "user.tests.test_user_delete_route",
    "app.tests.test_current_user_membership": "user.tests.test_current_user_membership",
    "app.tests.test_user_partial_patch": "user.tests.test_user_partial_patch",
    "app.tests.test_user_mmr_verification": "user.tests.test_user_mmr_verification",
    "app.tests.test_user_privilege_fields": "user.tests.test_user_privilege_fields",
    "app.tests.test_steam_account_id_conflict": "user.tests.test_steam_account_id_conflict",
    "app.schemas": "user.schemas",
    "app.user_cache": "user.cache",
    "app.tests.test_user_core_cache": "user.tests.test_user_core_cache",
    "app.tests.test_tournament_user_schema": "user.tests.test_tournament_user_schema",
    "app.tests.test_user_serializer_discord_names": "user.tests.test_user_serializer_discord_names",
    "app.tests.test_user_serializer_payload": "user.tests.test_user_serializer_payload",
    "app.tests.test_schema_reexports": "user.tests.test_schema_reexports",
    "app.tasks": None,
    "app.tasks.avatar_refresh": "user.tasks.avatar_refresh",
    "app.tasks.discord_name_sync": "user.tasks.discord_name_sync",
    "app.internal_client.users": "user.internal_client",
    "app.utils.avatar_utils": "user.avatar",
    "app.management.prod_payload": "user.management.prod_payload",
    "app.management.commands.refresh_avatars": "user.management.commands.refresh_avatars",
    "app.management.commands.sync_prod_users": "user.management.commands.sync_prod_users",
    "app.tests.test_avatar_refresh_batched": "user.tests.test_avatar_refresh_batched",
    "app.tests.test_discord_name_sync_task": "user.tests.test_discord_name_sync_task",
    "app.tests.test_discord_name_sync_beat": "user.tests.test_discord_name_sync_beat",
    "app.tests.test_prod_import_commands": "user.tests.test_prod_import_commands",
    "app.utils": None,
    "app.tests.test_league_rating": None,
    "app.permissions_tournament": "tournament.permissions",
    "app.tournament_state": "tournament.state",
    "app.tournament_list": "tournament.listing",
    "app.tournament_buckets": "tournament.buckets",
    "app.functions.tournament": "tournament.functions",
    "app.internal_client.tournaments": "tournament.internal_client",
    "app.views.admin_team": "tournament.views.members",
    "app.tests.test_tournament_migration": "tournament.tests.test_tournament_fields",
}

# target app -> production file (relative to backend/) -> what it may import from that app
ALLOWED_BACK_EDGES: dict[str, dict[str, BackEdge]] = {
    "draft": {},
    "org": {
        "app/views_main.py": BackEdge(
            frozenset({"Organization"}), "home_stats cross-domain aggregate"
        ),
        "app/admin.py": BackEdge(
            frozenset({"api", "release_earning_sends"}),
            "CustomUser admin delete checks standing blockers, releases promo "
            "earning sends and records standing on user deletion",
        ),
        "app/views/internal.py": BackEdge(
            frozenset({"OrgUser"}),
            "repeater subscriber endpoint reports each subscriber's org membership",
        ),
    },
    "league": {
        "app/views_main.py": BackEdge(
            frozenset({"League"}),
            "home_stats caches on and counts League as a cross-domain home-page "
            "aggregate",
        ),
    },
    "user": {
        "app/models.py": BackEdge(
            frozenset({"BaseUserProfile", "DotaUserProfile", "PositionsModel"}),
            "CustomUser profile accessors",
        ),
    },
    "tournament": {
        "app/exception_handler.py": BackEdge(
            frozenset({"PlacementRosterConflict", "TeamManagementError"}),
            "global DRF handler maps TeamManagementError and PlacementRosterConflict",
        ),
        "app/views_main.py": BackEdge(
            frozenset({"Game", "Tournament"}),
            "home_stats cross-domain aggregate",
        ),
    },
}

# (file relative to backend/, name) -> why a source-app module may define a moved name
ALLOWED_NAME_COLLISIONS: dict[tuple[str, str], str] = {
    ("app/tests/test_redis_namespace.py", "_reload"): (
        "Reloads backend.settings; unrelated to the moved user re-fetch helper."
    ),
    ("app/tests/test_settings_env_overrides.py", "_reload"): (
        "Reloads backend.settings; unrelated to the moved user re-fetch helper."
    ),
}

GUARD_FILE = "tests/test_app_boundaries.py"


def _module_of(path: str) -> str:
    parts = Path(path).with_suffix("").parts
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _package_of(path: str) -> str:
    module = _module_of(path)
    if Path(path).name == "__init__.py":
        return module
    return module.rpartition(".")[0]


def _resolve(node: ast.ImportFrom, path: str) -> str:
    if node.level == 0:
        return node.module or ""
    package = _package_of(path).split(".")
    base = package[: len(package) - (node.level - 1)] if node.level > 1 else package
    return ".".join([*base, node.module] if node.module else base)


def _within(name: str, prefix: str) -> bool:
    return name == prefix or name.startswith(f"{prefix}.")


def _is_label_reference(value: str, app_label: str, model_label: str) -> bool:
    label = f"{app_label}.{model_label}"
    folded = value.casefold()
    return folded == label or folded.startswith((f"{label}.", f"{label}_"))


def _is_command_module(module_name: str) -> bool:
    return ".management.commands." in f".{module_name}"


def _is_test_module(path: str) -> bool:
    p = Path(path)
    return "tests" in p.parts or p.name.startswith("test_")


def _top_level_names(tree: ast.Module) -> Iterator[tuple[str, int]]:
    for node in tree.body:
        if isinstance(node, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            yield node.name, node.lineno
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    yield target.id, node.lineno
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            yield node.target.id, node.lineno


def _top_level_defs(tree: ast.Module) -> Iterator[tuple[str, int]]:
    for node in tree.body:
        if isinstance(node, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            yield node.name, node.lineno


def _is_migration_code(path: str) -> bool:
    p = Path(path)
    return "migrations" in p.parts or (_is_test_module(path) and "migration" in p.stem)


def _is_type_checking(test: ast.expr) -> bool:
    return (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
        isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
    )


def _imported(
    tree: ast.Module, path: str
) -> Iterator[tuple[str, str | None, int, bool]]:
    """Yield (module, imported name or None for plain import, line, type_checking)."""
    type_checking: set[int] = {
        id(inner)
        for node in ast.walk(tree)
        if isinstance(node, ast.If) and _is_type_checking(node.test)
        for stmt in node.body
        for inner in ast.walk(stmt)
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name, None, node.lineno, id(node) in type_checking
        elif isinstance(node, ast.ImportFrom):
            module = _resolve(node, path)
            for alias in node.names:
                yield module, alias.name, node.lineno, id(node) in type_checking


def _back_edge_imports(
    tree: ast.Module, path: str, slices: tuple[MovedSlice, ...]
) -> dict[str, dict[str, bool]]:
    """new_app -> imported name -> whether every import of it is TYPE_CHECKING-only."""
    edges: dict[str, dict[str, bool]] = {}
    if _is_test_module(path):
        return edges
    for s in slices:
        if not _within(_module_of(path), s.source_app):
            continue
        for module, name, _line, type_checking in _imported(tree, path):
            if _within(module, s.new_app):
                names = edges.setdefault(s.new_app, {})
                key = name or module
                names[key] = names.get(key, True) and type_checking
    return edges


def collect_back_edges(
    source: str, path: str, slices: tuple[MovedSlice, ...] = MOVED_SLICES
) -> dict[str, set[str]]:
    if _is_test_module(path):
        return {}
    tree = ast.parse(source, filename=path)
    return {
        new_app: set(names)
        for new_app, names in _back_edge_imports(tree, path, slices).items()
    }


def find_violations(
    source: str,
    path: str,
    slices: tuple[MovedSlice, ...] = MOVED_SLICES,
    back_edges: dict[str, dict[str, BackEdge]] = ALLOWED_BACK_EDGES,
    collisions: dict[tuple[str, str], str] = ALLOWED_NAME_COLLISIONS,
) -> list[str]:
    tree = ast.parse(source, filename=path)
    module_name = _module_of(path)
    found: list[str] = []
    for s in slices:
        re_exports = {
            (_module_of(file), name)
            for file, edge in back_edges.get(s.new_app, {}).items()
            if file != path
            for name in edge.names
        }
        forbidden = s.moved | re_exports
        moved_here = {name for old, name in s.moved if old == module_name}
        for name, line in _top_level_names(tree):
            if name in moved_here:
                found.append(
                    f"{path}:{line}: [{s.name}] {name} redefined in {module_name}"
                )
        if _within(module_name, s.source_app):
            moved_names = {name for _old, name in s.moved} - moved_here
            command_module = _is_command_module(module_name)
            for name, line in _top_level_defs(tree):
                if name == "Command" and command_module:
                    continue
                if name in moved_names and (path, name) not in collisions:
                    found.append(
                        f"{path}:{line}: [{s.name}] moved name {name} redefined "
                        f"in {module_name}; not in ALLOWED_NAME_COLLISIONS"
                    )

        for module, name, line, _type_checking in _imported(tree, path):
            full = f"{module}.{name}" if name else module
            if name and (module, name) in forbidden:
                found.append(f"{path}:{line}: [{s.name}] imports {name} via {module}")
            if any(_within(module, r) or _within(full, r) for r in s.retired_modules):
                found.append(f"{path}:{line}: [{s.name}] imports retired module {full}")

        if not _is_migration_code(path):
            for line, what in _references_moved_model(tree, s):
                found.append(f"{path}:{line}: [{s.name}] {what}")
        prefixes = [f"{old}.{name}" for old, name in s.moved] + sorted(
            s.retired_modules
        )
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
                continue
            value = node.value
            is_label = any(
                _is_label_reference(value, s.source_app, label)
                for label in s.model_labels
            )
            if not is_label and any(_within(value, p) for p in prefixes):
                found.append(
                    f"{path}:{node.lineno}: [{s.name}] string back-door {value!r}"
                )

    for new_app, names in _back_edge_imports(tree, path, slices).items():
        allowed = back_edges.get(new_app, {}).get(path)
        if allowed is None:
            found.append(
                f"{path}: imports {sorted(names)} from {new_app}; not in ALLOWED_BACK_EDGES"
            )
            continue
        for name in sorted(names.keys() - allowed.names):
            found.append(
                f"{path}: imports {name} from {new_app}; not listed in ALLOWED_BACK_EDGES"
            )
        for name in sorted(allowed.type_only & names.keys()):
            if not names[name]:
                found.append(
                    f"{path}: imports {name} from {new_app} at runtime; "
                    "ALLOWED_BACK_EDGES allows it only under TYPE_CHECKING"
                )
    return found


def find_stale_back_edges(
    observed: dict[str, dict[str, set[str]]],
    back_edges: dict[str, dict[str, BackEdge]] = ALLOWED_BACK_EDGES,
) -> list[str]:
    stale: list[str] = []
    for new_app, files in back_edges.items():
        for path, edge in files.items():
            unused = edge.names - observed.get(new_app, {}).get(path, set())
            stale.extend(
                f"{path}: ALLOWED_BACK_EDGES[{new_app!r}] lists {name}, no longer imported"
                for name in sorted(unused)
            )
    return stale


def _migration_key(path: str) -> tuple[str, str]:
    p = Path(path)
    return p.parent.parent.name, p.stem


def _references_moved_model(
    tree: ast.Module, s: MovedSlice
) -> Iterator[tuple[int, str]]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if any(
                _is_label_reference(node.value, s.source_app, label)
                for label in s.model_labels
            ):
                yield node.lineno, f"lazy model label {node.value!r}"
        elif isinstance(node, ast.Call):
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else None
            if isinstance(func, ast.Name):
                name = func.id
            if name != "get_model" or len(node.args) < 2:
                continue
            app_arg, model_arg = node.args[0], node.args[1]
            if (
                isinstance(app_arg, ast.Constant)
                and app_arg.value == s.source_app
                and isinstance(model_arg, ast.Constant)
                and isinstance(model_arg.value, str)
                and model_arg.value.casefold() in s.model_labels
            ):
                yield (
                    node.lineno,
                    f"get_model({app_arg.value!r}, {model_arg.value!r})",
                )


def find_migration_ancestry_violations(
    slices: tuple[MovedSlice, ...],
    migration_files: Iterable[tuple[str, str]],
    ancestors: Callable[[tuple[str, str]], set[tuple[str, str]]],
) -> list[str]:
    """migration_files: (path like "<app>/migrations/<name>.py", source)."""
    files = list(migration_files)
    found: list[str] = []
    for s in slices:
        before_move: set[tuple[str, str]] | None = None
        for path, source in files:
            key = _migration_key(path)
            if key[0] == s.source_app:
                continue
            tree = ast.parse(source, path)
            lines = sorted({line for line, _ in _references_moved_model(tree, s)})
            if not lines:
                continue
            if before_move is None:
                before_move = ancestors(s.move_migration)
            if key not in before_move:
                found.append(
                    f"{path}:{lines[0]}: [{s.name}] uses {s.source_app} models moved by "
                    f"{'.'.join(s.move_migration)} but is not its ancestor"
                )
    return found


def _python_files(base: Path) -> Iterator[tuple[Path, str]]:
    for file in sorted(base.rglob("*.py")):
        rel = file.relative_to(base).as_posix()
        if "migrations" in Path(rel).parts or rel == GUARD_FILE:
            continue
        yield file, rel


def _migration_files(base: Path) -> Iterator[tuple[str, str]]:
    for file in sorted(base.rglob("*.py")):
        if file.parent.name == "migrations" and file.name != "__init__.py":
            yield file.relative_to(base).as_posix(), file.read_text()


def find_unlisted_retired_defs(
    slices: tuple[MovedSlice, ...],
    base: Path,
    homes: dict[str, str | None] = RETIRED_MODULE_HOMES,
    grandfathered: frozenset[str] = RETIRED_DEFS_GRANDFATHERED,
) -> list[str]:
    """Retired modules whose new home defines a top-level name not in `moved`."""
    found: list[str] = []
    for s in slices:
        if s.name in grandfathered:
            continue
        for module in sorted(s.retired_modules):
            if module in homes:
                home = homes[module]
            else:
                home = s.new_app + module.removeprefix(s.source_app)
            if home is None:
                continue
            path = base / Path(*home.split(".")).with_suffix(".py")
            if not path.exists():
                found.append(
                    f"[{s.name}] {module}: new home {home} not found; "
                    "map it in RETIRED_MODULE_HOMES"
                )
                continue
            listed = {name for old, name in s.moved if old == module}
            tree = ast.parse(path.read_text(), filename=str(path))
            for name, _line in _top_level_defs(tree):
                if name not in listed:
                    found.append(f"[{s.name}] {module}.{name} missing from moved")
    return found


FIXTURE_SLICE = MovedSlice(
    name="fixture",
    source_app="src",
    new_app="dst",
    moved=frozenset({("src.models", "Moved"), ("src.views", "MovedView")}),
    retired_modules=frozenset({"src.old"}),
    model_labels=frozenset({"moved"}),
    move_migration=("src", "0002_move"),
    cached_labels=frozenset({"moved"}),
)

FIXTURE_EDGES: dict[str, dict[str, BackEdge]] = {
    "dst": {
        "src/state.py": BackEdge(frozenset({"Moved"}), "fixture"),
        "src/models.py": BackEdge(
            frozenset({"Moved"}), "fixture", type_only=frozenset({"Moved"})
        ),
    },
}

FIXTURE_COLLISIONS: dict[tuple[str, str], str] = {
    ("src/client.py", "MovedView"): "fixture",
}

FIXTURE_MIGRATION = ("other", "0003_x")
FIXTURE_MIGRATION_PATH = "other/migrations/0003_x.py"


def _retired_module_present(base: Path, module: str) -> bool:
    rel = base / Path(*module.split("."))
    return rel.with_suffix(".py").exists() or (rel.is_dir() and any(rel.rglob("*.py")))


class GuardSelfTests(SimpleTestCase):
    def test_retired_package_with_leftover_py_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            package = base / "pkg"
            package.mkdir()
            (package / "x.py").write_text("")
            self.assertTrue(_retired_module_present(base, "pkg"))

    def test_retired_package_with_only_pycache_absent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            cache = base / "pkg" / "__pycache__"
            cache.mkdir(parents=True)
            (cache / "x.cpython-312.pyc").write_bytes(b"")
            self.assertFalse(_retired_module_present(base, "pkg"))

    def violations(self, source: str, path: str) -> list[str]:
        return find_violations(
            source,
            path,
            slices=(FIXTURE_SLICE,),
            back_edges=FIXTURE_EDGES,
            collisions=FIXTURE_COLLISIONS,
        )

    def assertFlagged(self, source: str, path: str) -> None:
        self.assertNotEqual(self.violations(source, path), [], source)

    def assertClean(self, source: str, path: str) -> None:
        self.assertEqual(self.violations(source, path), [], source)

    def ancestry(
        self, source: str, ancestors: set[tuple[str, str]], path: str
    ) -> list[str]:
        return find_migration_ancestry_violations(
            (FIXTURE_SLICE,), [(path, source)], lambda _key: ancestors
        )

    def test_redefinition_in_old_module(self) -> None:
        self.assertFlagged("class Moved:\n    pass\n", "src/models.py")
        self.assertFlagged("def MovedView():\n    pass\n", "src/views.py")
        self.assertFlagged("MovedView = object\n", "src/views.py")
        self.assertClean("class Other:\n    pass\n", "src/models.py")
        self.assertClean("class Moved:\n    pass\n", "dst/models.py")

    def test_absolute_import_through_old_module(self) -> None:
        self.assertFlagged("from src.models import Moved\n", "src/views.py")
        self.assertClean("from dst.models import Moved\n", "dst/views.py")
        self.assertClean("from src.models import Other\n", "src/views.py")

    def test_import_via_non_source_old_module_flagged(self) -> None:
        moved_slice = replace(
            FIXTURE_SLICE,
            moved=frozenset({("org.permissions", "f")}),
        )
        self.assertNotEqual(
            find_violations(
                "from org.permissions import f\n", "x/y.py", slices=(moved_slice,)
            ),
            [],
        )
        self.assertEqual(
            find_violations(
                "from user.permissions import f\n", "x/y.py", slices=(moved_slice,)
            ),
            [],
        )

    def test_relative_import_through_old_module(self) -> None:
        self.assertFlagged("from .models import Moved\n", "src/views.py")
        self.assertFlagged("from ..models import Moved\n", "src/views/foo.py")
        self.assertFlagged("from .views import MovedView\n", "src/__init__.py")
        self.assertClean("from .models import Other\n", "src/views.py")

    def test_retired_module_import(self) -> None:
        self.assertFlagged("import src.old\n", "tests/test_x.py")
        self.assertFlagged("from src import old\n", "tests/test_x.py")
        self.assertFlagged("from src.old import thing\n", "x.py")
        self.assertClean("from src import other\n", "tests/test_x.py")

    def test_patch_string_back_doors(self) -> None:
        self.assertFlagged('patch("src.models.Moved")\n', "x.py")
        self.assertFlagged('patch("src.views.MovedView.get")\n', "x.py")
        self.assertFlagged('patch("src.old.thing")\n', "x.py")
        self.assertFlagged('ForeignKey("src.Moved")\n', "x.py")
        self.assertFlagged('apps.get_model("SRC.moved")\n', "x.py")
        self.assertClean('patch("dst.models.Moved")\n', "x.py")
        self.assertClean('ForeignKey("dst.Moved")\n', "x.py")
        self.assertClean('patch("src.models.Other")\n', "x.py")

    def test_back_edge_unlisted_file(self) -> None:
        self.assertFlagged("from dst.models import Moved\n", "src/views/foo.py")
        self.assertFlagged("import dst.models\n", "src/views/foo.py")

    def test_back_edge_listed_file_unlisted_name(self) -> None:
        self.assertFlagged("from dst.models import Other\n", "src/state.py")
        self.assertClean("from dst.models import Moved\n", "src/state.py")

    def test_back_edge_stale_listed_name(self) -> None:
        observed: dict[str, dict[str, set[str]]] = {"dst": {}}
        self.assertNotEqual(find_stale_back_edges(observed, FIXTURE_EDGES), [])
        observed = {"dst": {"src/state.py": {"Moved"}, "src/models.py": {"Moved"}}}
        self.assertEqual(find_stale_back_edges(observed, FIXTURE_EDGES), [])

    def test_collect_back_edges_reports_observed_names(self) -> None:
        source = "from dst.models import Moved\nimport dst.views\n"
        self.assertEqual(
            collect_back_edges(source, "src/state.py", slices=(FIXTURE_SLICE,)),
            {"dst": {"Moved", "dst.views"}},
        )
        self.assertEqual(
            collect_back_edges(source, "src/tests/test_x.py", slices=(FIXTURE_SLICE,)),
            {},
        )

    def test_same_name_in_other_module_not_flagged(self) -> None:
        self.assertClean("from src.client import Moved\n", "x.py")
        self.assertClean('patch("src.client.Moved")\n', "x.py")

    def test_back_edge_names_not_reexported(self) -> None:
        self.assertFlagged("from src.state import Moved\n", "other/x.py")
        self.assertFlagged("from .state import Moved\n", "src/x.py")
        self.assertClean("from src.state import helper\n", "other/x.py")
        self.assertClean("from dst.models import Moved\n", "src/state.py")

    def test_test_modules_exempt_from_back_edges(self) -> None:
        self.assertClean("from dst.models import Moved\n", "src/tests/test_x.py")
        self.assertClean("from dst.models import Moved\n", "src/test_x.py")

    def test_non_source_app_files_exempt_from_back_edges(self) -> None:
        self.assertClean("from dst.models import Moved\n", "other/models.py")

    def test_type_only_name_allowed_under_type_checking(self) -> None:
        self.assertClean(
            "from typing import TYPE_CHECKING\n"
            "if TYPE_CHECKING:\n"
            "    from dst.models import Moved\n",
            "src/models.py",
        )
        self.assertClean(
            "import typing\nif typing.TYPE_CHECKING:\n    from dst.models import Moved\n",
            "src/models.py",
        )

    def test_type_only_name_flagged_at_runtime(self) -> None:
        self.assertFlagged("from dst.models import Moved\n", "src/models.py")
        self.assertFlagged(
            "from typing import TYPE_CHECKING\n"
            "if TYPE_CHECKING:\n"
            "    from dst.models import Moved\n"
            "else:\n"
            "    from dst.models import Moved\n",
            "src/models.py",
        )
        self.assertFlagged(
            "from typing import TYPE_CHECKING\n"
            "if TYPE_CHECKING:\n"
            "    pass\n"
            "from dst.models import Moved\n",
            "src/models.py",
        )

    def test_back_edge_reasons_non_empty(self) -> None:
        for new_app, files in ALLOWED_BACK_EDGES.items():
            for path, edge in files.items():
                with self.subTest(new_app=new_app, path=path):
                    self.assertTrue(edge.reason.strip())
                    self.assertTrue(edge.names)
                    self.assertLessEqual(edge.type_only, edge.names)

    def test_migration_ancestry_flags_non_ancestor(self) -> None:
        for source in (
            'Moved = apps.get_model("src", "Moved")\n',
            'Moved = apps.get_model("src.Moved")\n',
            'field = ForeignKey(to="src.moved")\n',
        ):
            with self.subTest(source=source):
                self.assertNotEqual(
                    self.ancestry(
                        source, {("src", "0001_initial")}, FIXTURE_MIGRATION_PATH
                    ),
                    [],
                )

    def test_migration_ancestry_accepts_ancestor(self) -> None:
        for source in (
            'Moved = apps.get_model("src", "Moved")\n',
            'Moved = apps.get_model("src.Moved")\n',
            'field = ForeignKey(to="src.moved")\n',
        ):
            with self.subTest(source=source):
                self.assertEqual(
                    self.ancestry(source, {FIXTURE_MIGRATION}, FIXTURE_MIGRATION_PATH),
                    [],
                )

    def test_migration_ancestry_ignores_unrelated_and_source_app(self) -> None:
        self.assertEqual(
            self.ancestry(
                'apps.get_model("src", "Other")\n', set(), FIXTURE_MIGRATION_PATH
            ),
            [],
        )
        self.assertEqual(
            self.ancestry(
                'apps.get_model("dst", "Moved")\n', set(), FIXTURE_MIGRATION_PATH
            ),
            [],
        )
        self.assertEqual(
            self.ancestry(
                'apps.get_model("src", "Moved")\n', set(), "src/migrations/0003_x.py"
            ),
            [],
        )

    def test_migration_ancestry_checks_new_app_migrations(self) -> None:
        path = "dst/migrations/0003_x.py"
        source = 'apps.get_model("src", "Moved")\n'
        violations = self.ancestry(source, set(), path)
        self.assertEqual(len(violations), 1)
        self.assertIn(path, violations[0])
        self.assertEqual(self.ancestry(source, {("dst", "0003_x")}, path), [])

    def unlisted_retired_defs(
        self, source: str, homes: dict[str, str | None] | None = None
    ) -> list[str]:
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "dst").mkdir()
            (Path(tmp) / "dst" / "old.py").write_text(source)
            return find_unlisted_retired_defs(
                (FIXTURE_SLICE,), Path(tmp), homes or {}, frozenset()
            )

    def test_retired_module_def_missing_from_moved(self) -> None:
        found = self.unlisted_retired_defs("class Moved:\n    pass\n")
        self.assertEqual(found, ["[fixture] src.old.Moved missing from moved"])

    def test_retired_module_home_not_found(self) -> None:
        found = self.unlisted_retired_defs("", {"src.old": "dst.renamed"})
        self.assertEqual(len(found), 1)
        self.assertIn("RETIRED_MODULE_HOMES", found[0])

    def test_retired_module_renamed_in_source_app_skipped(self) -> None:
        found = self.unlisted_retired_defs(
            "def gone() -> None: ...\n", {"src.old": None}
        )
        self.assertEqual(found, [])

    def test_two_argument_get_model(self) -> None:
        self.assertFlagged('apps.get_model("src", "Moved")\n', "x.py")
        self.assertFlagged('apps.get_model("src", "moved")\n', "src/signals.py")
        self.assertFlagged('get_model("src", "Moved")\n', "x.py")
        self.assertClean('apps.get_model("dst", "Moved")\n', "x.py")
        self.assertClean('apps.get_model("src", "Other")\n', "x.py")

    def test_migration_code_exempt_from_lazy_labels(self) -> None:
        for path in (
            "src/migrations/0003_x.py",
            "other/migrations/0003_x.py",
            "other/tests/test_x_migration.py",
        ):
            with self.subTest(path=path):
                self.assertClean('apps.get_model("src", "Moved")\n', path)
                self.assertClean('apps.get_model("src.Moved")\n', path)
                self.assertFlagged('patch("src.models.Moved")\n', path)
        self.assertFlagged('apps.get_model("src", "Moved")\n', "other/tests/test_x.py")

    def test_redefinition_in_new_module(self) -> None:
        self.assertFlagged("class Moved(models.Model):\n    pass\n", "src/new.py")
        self.assertFlagged("def MovedView():\n    pass\n", "src/views/extra.py")
        self.assertFlagged("async def MovedView():\n    pass\n", "src/tests/test_x.py")
        self.assertClean("class Moved:\n    pass\n", "other/new.py")
        self.assertClean("class Moved:\n    pass\n", "dst/new.py")
        self.assertClean(
            "class Other:\n    def Moved(self):\n        pass\n", "src/new.py"
        )

    def test_allowlisted_name_collision(self) -> None:
        self.assertClean("def MovedView():\n    pass\n", "src/client.py")
        self.assertFlagged("class Moved:\n    pass\n", "src/client.py")
        self.assertFlagged("def MovedView():\n    pass\n", "src/other.py")

    def test_name_collision_reasons_non_empty(self) -> None:
        for (path, name), reason in ALLOWED_NAME_COLLISIONS.items():
            with self.subTest(path=path, name=name):
                self.assertTrue(reason.strip())

    def test_label_reference_matches_through_model_string(self) -> None:
        self.assertFlagged(
            'm2m_changed.connect(f, sender="src.Moved_members")\n', "x.py"
        )
        self.assertFlagged('SENDER = "SRC.moved_users"\n', "x.py")
        self.assertClean('SENDER = "dst.Moved_members"\n', "x.py")
        self.assertTrue(_is_label_reference("app.Team_members", "app", "team"))

    def test_label_reference_matches_dotted_field_key(self) -> None:
        self.assertFlagged('EXCLUDED = {"src.Moved.team"}\n', "x.py")
        self.assertClean('EXCLUDED = {"dst.Moved.team"}\n', "x.py")
        self.assertTrue(_is_label_reference("app.TeamLog.team", "app", "teamlog"))

    def test_label_reference_rejects_near_miss(self) -> None:
        self.assertClean('LABEL = "src.movedx"\n', "x.py")
        self.assertClean('LABEL = "src.Movedx.team"\n', "x.py")
        self.assertClean('LABEL = "src.mov"\n', "x.py")
        self.assertFalse(_is_label_reference("app.teamlogx", "app", "teamlog"))

    def command_violations(self, source: str, path: str) -> list[str]:
        command_slice = replace(
            FIXTURE_SLICE,
            moved=FIXTURE_SLICE.moved | {("src.old", "Command")},
        )
        return find_violations(
            source, path, slices=(command_slice,), back_edges={}, collisions={}
        )

    def test_command_in_source_app_command_module_not_flagged(self) -> None:
        source = "class Command(BaseCommand):\n    pass\n"
        self.assertEqual(
            self.command_violations(source, "src/management/commands/x.py"), []
        )

    def test_command_outside_command_module_still_flagged(self) -> None:
        source = "class Command(BaseCommand):\n    pass\n"
        self.assertNotEqual(self.command_violations(source, "src/x.py"), [])
        self.assertNotEqual(self.command_violations(source, "src/management/x.py"), [])

    def test_split_retirement_cross_app_names_listed_same_app_names_not(
        self,
    ) -> None:
        split = replace(
            FIXTURE_SLICE,
            moved=frozenset({("src.old", "to_new_app"), ("src.old", "to_third_app")}),
        )

        def violations(source: str, path: str) -> list[str]:
            return find_violations(
                source, path, slices=(split,), back_edges={}, collisions={}
            )

        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "dst").mkdir()
            (Path(tmp) / "dst" / "old.py").write_text("def to_new_app() -> None: ...\n")
            self.assertEqual(
                find_unlisted_retired_defs((split,), Path(tmp), {}, frozenset()), []
            )
        self.assertEqual(violations("def stays() -> None: ...\n", "src/renamed.py"), [])
        self.assertEqual(
            violations("def to_third_app() -> None: ...\n", "other/thing.py"), []
        )
        self.assertEqual(violations("from src.renamed import stays\n", "x.py"), [])
        self.assertEqual(
            violations("from other.thing import to_third_app\n", "x.py"), []
        )
        self.assertNotEqual(violations("from src.old import stays\n", "x.py"), [])
        self.assertNotEqual(
            violations("def to_third_app() -> None: ...\n", "src/renamed.py"), []
        )


class AppBoundaryTests(SimpleTestCase):
    base: Path = settings.BASE_DIR_PATH

    def test_no_moved_code_reachable_through_source_app(self) -> None:
        violations: list[str] = []
        observed: dict[str, dict[str, set[str]]] = {}
        for file, rel in _python_files(self.base):
            source = file.read_text()
            violations.extend(find_violations(source, rel))
            for new_app, names in collect_back_edges(source, rel).items():
                observed.setdefault(new_app, {})[rel] = names
        violations.extend(find_stale_back_edges(observed))
        self.assertEqual(violations, [])

    def test_name_collisions_not_stale(self) -> None:
        moved = {name for s in MOVED_SLICES for _old, name in s.moved}
        for path, name in ALLOWED_NAME_COLLISIONS:
            with self.subTest(path=path, name=name):
                self.assertIn(name, moved)
                tree = ast.parse((self.base / path).read_text(), filename=path)
                self.assertIn(name, {defined for defined, _ in _top_level_defs(tree)})

    def test_walk_covers_the_tree(self) -> None:
        rels = {rel for _file, rel in _python_files(self.base)}
        self.assertIn("app/models.py", rels)
        self.assertIn("draft/models/hero.py", rels)
        self.assertIn("draft/models/team.py", rels)
        self.assertIn("org/permissions.py", rels)
        self.assertIn("user/permissions.py", rels)
        self.assertIn("backend/settings.py", rels)
        self.assertIn("config/celery_light.py", rels)
        self.assertIn("org/models.py", rels)
        self.assertIn("league/permissions.py", rels)
        self.assertIn("league/models.py", rels)
        self.assertIn("league/models_rating.py", rels)
        self.assertIn("tournament/permissions.py", rels)
        self.assertIn("tournament/views/team.py", rels)
        self.assertIn("tournament/consumers.py", rels)
        self.assertIn("tournament/models/team.py", rels)
        self.assertNotIn(GUARD_FILE, rels)
        self.assertFalse(any("/migrations/" in rel for rel in rels))

    def test_retired_modules_are_gone(self) -> None:
        for s in MOVED_SLICES:
            for module in s.retired_modules:
                with self.subTest(module=module):
                    self.assertFalse(_retired_module_present(self.base, module))

    def test_retired_module_defs_listed_in_moved(self) -> None:
        self.assertEqual(find_unlisted_retired_defs(MOVED_SLICES, self.base), [])

    def test_new_apps_registered(self) -> None:
        labels = {entry.split(".")[0] for entry in MODEL_APPS}
        for s in MOVED_SLICES:
            with self.subTest(slice=s.name):
                self.assertIn(s.new_app, labels)

    def test_no_cacheops_key_for_moved_models(self) -> None:
        keys = {key.casefold() for key in settings.CACHEOPS}
        for s in MOVED_SLICES:
            for label in s.model_labels:
                with self.subTest(label=label):
                    self.assertNotIn(f"{s.source_app}.{label}", keys)

    def test_new_cacheops_keys_present(self) -> None:
        for s in MOVED_SLICES:
            for label in s.cached_labels:
                with self.subTest(label=label):
                    self.assertIn(f"{s.new_app}.{label}", settings.CACHEOPS)

    def test_cross_app_migrations_precede_move(self) -> None:
        graph = MigrationLoader(None, ignore_no_migrations=True).graph
        files = list(_migration_files(self.base))
        self.assertTrue(files)
        violations = find_migration_ancestry_violations(
            MOVED_SLICES, files, lambda key: set(graph.forwards_plan(key))
        )
        self.assertEqual(violations, [])

    def test_moved_models_keep_their_tables(self) -> None:
        for s in MOVED_SLICES:
            for label in s.model_labels:
                with self.subTest(label=label):
                    model = apps.get_model(s.new_app, label)
                    self.assertEqual(model._meta.app_label, s.new_app)
                    self.assertEqual(model._meta.db_table, f"{s.source_app}_{label}")
