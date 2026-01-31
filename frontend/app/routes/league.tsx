import { generateMeta } from '~/lib/seo';
import { fetchLeague } from '~/components/api/api';
import { useParams, useNavigate } from 'react-router';
import type { Route } from './+types/league';

export async function loader({ params }: Route.LoaderArgs) {
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
import { useState, useEffect } from 'react';
import { Trophy, Building2, Loader2, Pencil } from 'lucide-react';

import { Badge } from '~/components/ui/badge';
import { Button } from '~/components/ui/button';
import { useLeague, LeagueTabs, EditLeagueModal } from '~/components/league';
import { useUserStore } from '~/store/userStore';
import { useIsLeagueAdmin } from '~/hooks/usePermissions';

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

  const handleTabChange = (newTab: string) => {
    setActiveTab(newTab);
    navigate(`/leagues/${leagueId}/${newTab}`, { replace: true });
  };

  // Filter tournaments for this league
  const leagueTournaments = tournaments?.filter(
    (t) => t.league === pk
  ) || [];

  // Permission check for edit - includes org admins via useIsLeagueAdmin
  const canEdit = useIsLeagueAdmin(league);

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
    <div className="container mx-auto py-6 space-y-6">
        {/* Header */}
        <div className="flex items-start justify-between">
          <div className="space-y-2">
            <div className="flex items-center gap-3">
              <Trophy className="h-8 w-8 text-primary" />
              <h1 className="text-3xl font-bold">{league.name}</h1>
            </div>
            <div className="flex items-center gap-2 text-muted-foreground">
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
            <Button
              variant="outline"
              size="sm"
              onClick={() => setEditModalOpen(true)}
              data-testid="edit-league-button"
            >
              <Pencil className="h-4 w-4 mr-2" />
              Edit League
            </Button>
          )}
        </div>

        {/* Tabs */}
        <LeagueTabs
          league={league}
          tournaments={leagueTournaments}
          activeTab={activeTab}
          onTabChange={handleTabChange}
        />

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
