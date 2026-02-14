import { generateMeta } from '~/lib/seo';
import { fetchLeague } from '~/components/api/api';
import { useParams, useNavigate } from 'react-router';
import type { Route } from './+types/league';

export async function clientLoader({ params }: Route.ClientLoaderArgs) {
  const pk = params.leagueId ? parseInt(params.leagueId, 10) : null;
  if (!pk) return { league: null };

  try {
    const league = await fetchLeague(pk);
    return { league };
  } catch {
    return { league: null };
  }
}

export function meta({ data }: Route.MetaArgs) {
  const league = data?.league;

  if (league?.name) {
    const orgName = league.organization_name ? ` by ${league.organization_name}` : '';
    return generateMeta({
      title: league.name,
      description: `${league.name}${orgName} - League standings and tournament schedule`,
      url: `/leagues/${league.pk}`,
    });
  }

  return generateMeta({
    title: 'League',
    description: 'League standings and tournament schedule',
  });
}
import { useState, useEffect, useMemo, useCallback } from 'react';
import { Trophy, Building2, Loader2, Pencil } from 'lucide-react';

import { Badge } from '~/components/ui/badge';
import { PrimaryButton } from '~/components/ui/buttons';
import { useLeague, LeagueTabs, EditLeagueModal } from '~/components/league';
import { useUserStore } from '~/store/userStore';
import { useOrgStore } from '~/store/orgStore';
import { useLeagueStore } from '~/store/leagueStore';
import { useIsLeagueAdmin } from '~/hooks/usePermissions';
import { usePageNav } from '~/hooks/usePageNav';

export default function LeaguePage() {
  const { leagueId, tab } = useParams<{ leagueId: string; tab?: string }>();
  const navigate = useNavigate();
  const pk = leagueId ? parseInt(leagueId, 10) : undefined;

  const { league, isLoading, error, refetch } = useLeague(pk);
  const currentUser = useUserStore((state) => state.currentUser);
  const tournaments = useUserStore((state) => state.tournaments);
  const getTournaments = useUserStore((state) => state.getTournaments);

  const [activeTab, setActiveTab] = useState(tab || 'info');
  const [editModalOpen, setEditModalOpen] = useState(false);

  // Fetch tournaments
  useEffect(() => {
    getTournaments();
  }, [getTournaments]);

  // Sync tab with URL - only react to URL changes
  useEffect(() => {
    if (tab && tab !== activeTab) {
      setActiveTab(tab);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab]);

  // Set org and league context for child components (e.g. UsersTab)
  useEffect(() => {
    if (league) {
      useOrgStore.getState().setCurrentOrg(league.organization ?? null);
      useLeagueStore.getState().setCurrentLeague(league);
    }

    return () => {
      useOrgStore.getState().setCurrentOrg(null);
      useLeagueStore.getState().setCurrentLeague(null);
    };
  }, [league]);

  const handleTabChange = useCallback((newTab: string) => {
    setActiveTab(newTab);
    // Don't use replace: true - we want history entries for browser back/forward
    navigate(`/leagues/${leagueId}/${newTab}`);
  }, [leagueId, navigate]);

  // Filter tournaments for this league
  // league can be a number (ID) or object (from list endpoint with pk, name, organization_name)
  const leagueTournaments = tournaments?.filter((t) => {
    const leagueId = typeof t.league === 'object' ? t.league?.pk : t.league;
    return leagueId === pk || t.league_pk === pk;
  }) || [];

  // Permission check for edit - includes org admins via useIsLeagueAdmin
  const canEdit = useIsLeagueAdmin(league);

  // Page nav options for mobile navbar dropdown
  const leagueUserPks = useLeagueStore((s) => s.leagueUserPks);
  const leagueUsersLoading = useLeagueStore((s) => s.leagueUsersLoading);
  const leagueUsersLeagueId = useLeagueStore((s) => s.leagueUsersLeagueId);
  const userCountDisplay = leagueUsersLoading || leagueUsersLeagueId !== pk
    ? '...' : leagueUserPks.length;

  const pageNavOptions = useMemo(() => [
    { value: 'info', label: 'Info' },
    { value: 'tournaments', label: `${leagueTournaments.length} Tourneys` },
    { value: 'users', label: `${userCountDisplay} Users` },
    { value: 'matches', label: 'Matches' },
  ], [leagueTournaments.length, userCountDisplay]);

  usePageNav(league ? pageNavOptions : null, activeTab, handleTabChange);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error || !league) {
    return (
      <div className="text-center py-12 text-destructive">
        {error?.message || 'League not found'}
      </div>
    );
  }

  return (
    <div className="container mx-auto py-6 px-4 space-y-6">
      <div className="flex flex-col gap-6 rounded-lg border border-border bg-base-200/50 p-4 md:p-6">
        {/* Header */}
        <div className="flex flex-col sm:flex-row items-start sm:justify-between gap-3">
          <div className="space-y-2 min-w-0">
            <div className="flex items-center gap-3">
              <Trophy className="h-7 w-7 md:h-8 md:w-8 text-primary shrink-0" />
              <h1 className="text-xl! md:text-3xl! font-bold truncate">{league.name}</h1>
            </div>
            <div className="flex flex-wrap items-center gap-2 text-muted-foreground">
              {league.organization_name && (
                <Badge variant="outline" className="flex items-center gap-1">
                  <Building2 className="h-3 w-3" />
                  {league.organization_name}
                </Badge>
              )}
              {league.steam_league_id && (
                <Badge variant="secondary">
                  Steam ID: {league.steam_league_id}
                </Badge>
              )}
            </div>
          </div>

          {canEdit && (
            <PrimaryButton
              size="sm"
              onClick={() => setEditModalOpen(true)}
              data-testid="edit-league-button"
              className="shrink-0 w-full sm:w-auto"
            >
              <Pencil className="h-4 w-4 mr-2" />
              Edit League
            </PrimaryButton>
          )}
        </div>

        {/* Tabs */}
        <LeagueTabs
          league={league}
          tournaments={leagueTournaments}
          activeTab={activeTab}
          onTabChange={handleTabChange}
        />
      </div>

      {/* Edit Modal */}
      {canEdit && league && (
        <EditLeagueModal
          open={editModalOpen}
          onOpenChange={setEditModalOpen}
          league={league}
          onSuccess={refetch}
        />
      )}
    </div>
  );
}
