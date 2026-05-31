import React, { useEffect, useMemo, useState } from 'react';
import { useParams, useNavigate } from 'react-router';
import { Pencil, Trash2, ShieldAlert } from 'lucide-react';
import type { UserType } from '~/components/user/types';
import { useLeagueStore } from '~/store/leagueStore';
import { useOrgStore } from '~/store/orgStore';
import { useTournamentStore } from '~/store/tournamentStore';
import { useUserCacheStore } from '~/store/userCacheStore';
import { useUserStore } from '~/store/userStore';
import { useTournament } from '~/hooks/useTournament';
import { useTournamentSocket } from '~/hooks/useTournamentSocket';
import { hydrateTournament } from '~/lib/hydrateTournament';
import { deleteTournament } from '~/components/api/api';
import type { TournamentType } from '~/components/tournament/types';
import TournamentTabs from './tabs/TournamentTabs';
import { EntityBreadcrumb, type BreadcrumbSegment } from '~/components/ui/entity-breadcrumb';
import { PageHeader } from '~/components/ui/page-header';
import { TournamentSettingsModal } from '~/components/tournament/settings/TournamentSettingsModal';
import { DestructiveButton, EditButton } from '~/components/ui/buttons';
import { BrandDropdownMenu, type BrandDropdownAction } from '~/components/ui/brand-dropdown-menu';
import { ConfirmDialog } from '~/components/ui/dialogs';
import { toast } from 'sonner';

import { getLogger } from '~/lib/logger';
const log = getLogger('TournamentDetailPage');

export const TournamentDetailPage: React.FC = () => {
  const { pk, '*': slug } = useParams<{ pk: string; '*': string }>();
  const navigate = useNavigate();
  const pkNum = pk ? parseInt(pk, 10) : null;

  const currentUser = useUserStore((state) => state.currentUser);

  // TanStack Query for tournament data
  const { data: tournament, isLoading, error } = useTournament(
    pkNum && !Number.isNaN(pkNum) ? pkNum : null,
  );

  // WebSocket for real-time cache invalidation
  useTournamentSocket(pkNum && !Number.isNaN(pkNum) ? pkNum : null);

  // Hydrate slim tournament response: resolve PK-only user references
  // back to full objects using the _users dict, so downstream consumers
  // continue to receive UserType objects.
  const hydratedTournament = useMemo(() => {
    if (!tournament) return null;
    return hydrateTournament(tournament as TournamentType & { _users?: Record<number, UserType> });
  }, [tournament]);

  // Sync hydrated data to userStore for ~35 existing consumers
  useEffect(() => {
    if (hydratedTournament) {
      // Ingest _users dict into entity cache for cross-page deduplication
      const _users = (tournament as Record<string, unknown>)?._users as
        | Record<number, UserType>
        | undefined;
      if (_users) {
        const users = Object.values(_users);
        const orgId = hydratedTournament.organization_pk ?? useOrgStore.getState().currentOrg?.pk;
        const leagueId = hydratedTournament.league_pk ?? undefined;
        useUserCacheStore.getState().upsert(users, { orgId, leagueId });
      }
      useUserStore.getState().setTournament(hydratedTournament);
    }
    return () => {
      useUserStore.getState().setTournament(null);
    };
  }, [hydratedTournament]);

  const breadcrumbSegments = useMemo((): BreadcrumbSegment[] => {
    if (!tournament) return [];
    const segments: BreadcrumbSegment[] = [];

    // Organization (from league)
    const league = typeof tournament.league === 'object' ? tournament.league : null;
    if (league?.organization_name && tournament.organization_pk) {
      segments.push({
        type: 'organization',
        label: league.organization_name,
        href: `/organizations/${tournament.organization_pk}`,
      });
    }

    // League
    if (league) {
      segments.push({
        type: 'league',
        label: league.name,
        href: `/leagues/${league.pk}`,
      });
    }

    // Event Series (from source_event.event_repeater)
    const sourceEvent = tournament.source_event;
    if (sourceEvent?.event_repeater) {
      segments.push({
        type: 'event-series',
        label: sourceEvent.event_repeater.name,
      });
    }

    // Event (from source_event)
    if (sourceEvent) {
      segments.push({
        type: 'event',
        label: sourceEvent.name,
        href: `/events/${sourceEvent.id}`,
      });
    }

    // Tournament (current page)
    if (tournament.name) {
      segments.push({
        type: 'tournament',
        label: tournament.name,
      });
    }

    return segments;
  }, [tournament]);

  // UI state from tournamentStore
  const setLive = useTournamentStore((state) => state.setLive);
  const setActiveTab = useTournamentStore((state) => state.setActiveTab);
  const setAutoAdvance = useTournamentStore((state) => state.setAutoAdvance);
  const setPendingDraftId = useTournamentStore((state) => state.setPendingDraftId);
  const setPendingMatchId = useTournamentStore((state) => state.setPendingMatchId);

  // Parse URL slug for tabs and deep-linking
  useEffect(() => {
    const parts = slug?.split('/') || [];
    let tab = parts[0] || 'players';
    if (tab === 'games') {
      tab = 'bracket';
    }
    const isLive = parts[1] === 'draft';
    const draftId = parts[1] === 'draft' && parts[2] ? parseInt(parts[2], 10) : null;
    const matchId = parts[1] === 'match' && parts[2] ? parts[2] : null;

    // Redirect /tournament/:pk/bracket/draft/:draftId to /herodraft/:draftId
    if (draftId && !Number.isNaN(draftId)) {
      navigate(`/herodraft/${draftId}`, { replace: true });
      return;
    }

    setActiveTab(tab);
    setPendingDraftId(Number.isNaN(draftId) ? null : draftId);
    setPendingMatchId(matchId);
    setLive(isLive);
    if (isLive) {
      setAutoAdvance(true);
    }
  }, [slug, setActiveTab, setLive, setAutoAdvance, setPendingDraftId, setPendingMatchId, navigate]);

  // Set org context from tournament
  useEffect(() => {
    if (tournament?.organization_pk) {
      useOrgStore.getState().getOrganization(tournament.organization_pk);
    } else {
      useOrgStore.getState().setCurrentOrg(null);
    }
    return () => {
      useOrgStore.getState().reset();
    };
  }, [tournament?.organization_pk]);

  // Set league context from tournament
  useEffect(() => {
    if (tournament?.league_pk) {
      useLeagueStore.getState().getLeague(tournament.league_pk);
    } else {
      useLeagueStore.getState().setCurrentLeague(null);
    }
    return () => {
      useLeagueStore.getState().reset();
    };
  }, [tournament?.league_pk]);

  const [settingsOpen, setSettingsOpen] = useState(false);
  const [showDeleteTournament, setShowDeleteTournament] = useState(false);
  const isAdmin = currentUser?.is_staff || currentUser?.is_superuser;

  const openDeleteDialog = () => {
    if (!tournament?.pk) return;
    setShowDeleteTournament(true);
  };

  const handleDelete = async () => {
    if (!tournament?.pk) return;
    try {
      await deleteTournament(tournament.pk);
      toast.success('Tournament deleted');
      navigate(-1);
    } catch {
      toast.error('Failed to delete tournament');
    }
  };

  const adminActions = useMemo((): BrandDropdownAction[] => {
    if (!isAdmin || !tournament) return [];
    return [
      {
        key: 'edit',
        icon: <Pencil className="h-4 w-4 mr-1.5" />,
        label: 'Edit',
        onClick: () => setSettingsOpen(true),
        variant: 'edit',
        'data-testid': 'tournament-edit-btn',
      },
      {
        key: 'delete',
        icon: <Trash2 className="h-4 w-4 mr-1.5" />,
        label: 'Delete',
        onClick: openDeleteDialog,
        variant: 'destructive',
        'data-testid': 'tournament-delete-btn',
      },
    ];
  }, [isAdmin, tournament]);

  if (isLoading) {
    return (
      <div className="flex justify-center items-center h-screen">
        <span className="loading loading-spinner loading-lg"></span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex justify-center items-center h-screen">
        <div role="alert" className="alert alert-error">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            className="stroke-current shrink-0 h-6 w-6"
            fill="none"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth="2"
              d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z"
            />
          </svg>
          <span>Failed to load tournament details. Please try again later.</span>
        </div>
      </div>
    );
  }

  if (!tournament) {
    return (
      <div className="flex justify-center items-center h-screen">
        Tournament not found.
      </div>
    );
  }

  const getDate = () => {
    if (!tournament.date_played) return '';
    const d = new Date(tournament.date_played);
    if (Number.isNaN(d.getTime())) return '';
    return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
  };

  const title = () => {
    if (!tournament.name) return null;
    const adminActionsNode = isAdmin && hydratedTournament && (
      <div className="flex items-center gap-2 mb-3">
        {/* Desktop: brand Edit + Delete pair, equal min-width so the
            shorter label doesn't render a visibly narrower pill. */}
        <div className="hidden md:flex items-center gap-2">
          <EditButton
            size="sm"
            className="min-w-24 justify-center"
            onClick={() => setSettingsOpen(true)}
            data-testid="tournament-edit-btn"
          >
            <Pencil className="h-4 w-4 mr-1.5" />
            Edit
          </EditButton>
          <DestructiveButton
            size="sm"
            className="min-w-24 justify-center"
            onClick={openDeleteDialog}
            data-testid="tournament-delete-btn"
          >
            <Trash2 className="h-4 w-4 mr-1.5" />
            Delete
          </DestructiveButton>
        </div>
        {/* Mobile: dropdown */}
        <div className="md:hidden">
          <BrandDropdownMenu
            label="Admin"
            icon={<ShieldAlert className="h-4 w-4 mr-1.5" />}
            actions={adminActions}
            variant="admin"
            data-testid="tournament-admin-actions-mobile"
          />
        </div>
        <TournamentSettingsModal
          tournament={hydratedTournament}
          open={settingsOpen}
          onOpenChange={setSettingsOpen}
        />
      </div>
    );
    const playedOn = getDate();
    return (
      <PageHeader
        title={tournament.name}
        subtitle={
          playedOn ? (
            <span className="text-sm sm:text-base text-muted-foreground">
              played on {playedOn}
            </span>
          ) : undefined
        }
        actions={adminActionsNode || undefined}
        data-testid="tournamentTitle"
      />

    );
  };

  return (
    <div
      className="max-w-full overflow-x-hidden px-3 py-3 sm:container sm:mx-auto sm:p-4"
      data-testid="tournamentDetailPage"
    >
      {breadcrumbSegments.length > 1 && <EntityBreadcrumb segments={breadcrumbSegments} />}
      {title()}
      <TournamentTabs />
      <ConfirmDialog
        open={showDeleteTournament}
        onOpenChange={setShowDeleteTournament}
        title="Delete tournament?"
        description={
          <>
            This will permanently delete <strong>{tournament?.name}</strong>, its brackets, matches, and signups. This cannot be undone.
          </>
        }
        confirmLabel="Delete tournament"
        variant="destructive"
        onConfirm={handleDelete}
        contentTestId="delete-tournament-dialog"
        confirmTestId="delete-tournament-confirm"
        cancelTestId="delete-tournament-cancel"
      />
    </div>
  );
};

export default TournamentDetailPage;
