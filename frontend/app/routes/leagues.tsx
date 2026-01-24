import { Plus, Trophy } from 'lucide-react';
import { memo, useEffect, useState, useMemo } from 'react';
import { useSearchParams } from 'react-router';
import {
  CreateLeagueModal,
  LeagueCard,
  useLeagues,
} from '~/components/league';
import type { LeagueType } from '~/components/league/schemas';
import { useOrganizations } from '~/components/organization';
import { Button } from '~/components/ui/button';
import { Card, CardContent, CardHeader } from '~/components/ui/card';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '~/components/ui/select';
import { useUserStore } from '~/store/userStore';
import { useIsOrganizationAdmin } from '~/hooks/usePermissions';

/** Skeleton loader for league cards */
const LeagueCardSkeleton = () => (
  <Card className="animate-pulse">
    <CardHeader>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-5 h-5 rounded bg-base-300" />
          <div className="h-5 w-32 bg-base-300 rounded" />
        </div>
        <div className="h-5 w-16 bg-base-300 rounded" />
      </div>
      <div className="h-4 w-24 bg-base-300 rounded mt-2" />
    </CardHeader>
    <CardContent>
      <div className="h-4 w-3/4 bg-base-300 rounded mb-2" />
      <div className="h-4 w-1/2 bg-base-300 rounded" />
    </CardContent>
  </Card>
);

/** Grid of skeleton cards for initial loading */
const LeagueGridSkeleton = ({ count = 6 }: { count?: number }) => (
  <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
    {Array.from({ length: count }).map((_, index) => (
      <LeagueCardSkeleton key={`skeleton-${index}`} />
    ))}
  </div>
);

/** Empty state when no leagues found */
const EmptyLeagues = ({ hasOrgFilter }: { hasOrgFilter: boolean }) => (
  <div className="flex flex-col items-center justify-center py-16 text-base-content/60">
    <Trophy className="w-16 h-16 mb-4 opacity-50" />
    <h3 className="text-xl font-semibold mb-2">No Leagues Found</h3>
    <p className="text-sm text-muted-foreground">
      {hasOrgFilter
        ? 'No leagues found for this organization'
        : 'Create a new league to get started!'}
    </p>
  </div>
);

/** Memoized wrapper for individual league cards */
const LeagueCardWrapper = memo(({
  league,
}: {
  league: LeagueType;
}) => {
  return <LeagueCard league={league} />;
});

// Try to get cached leagues from sessionStorage (client-side only)
const getCachedLeagues = (): LeagueType[] => {
  try {
    const stored = sessionStorage.getItem('dtx-storage');
    if (stored) {
      const parsed = JSON.parse(stored);
      return parsed?.state?.leagues || [];
    }
  } catch {
    // Ignore parse errors
  }
  return [];
};

export default function LeaguesPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedOrgId = searchParams.get('organization');
  const selectedOrgIdNum = selectedOrgId ? parseInt(selectedOrgId, 10) : null;

  const { leagues: storeLeagues, isLoading } = useLeagues(selectedOrgIdNum ?? undefined);
  const { organizations } = useOrganizations();
  const currentUser = useUserStore((state) => state.currentUser);
  const hasHydrated = useUserStore((state) => state.hasHydrated);
  const [createModalOpen, setCreateModalOpen] = useState(false);

  // Get selected organization for permission checks
  const selectedOrg = useMemo(
    () => organizations.find((o) => o.pk === selectedOrgIdNum) || null,
    [organizations, selectedOrgIdNum]
  );
  const isOrgAdmin = useIsOrganizationAdmin(selectedOrg);

  // Read cached leagues after mount to avoid hydration mismatch
  const [mounted, setMounted] = useState(false);
  const [cachedLeagues, setCachedLeagues] = useState<LeagueType[]>([]);

  useEffect(() => {
    setMounted(true);
    setCachedLeagues(getCachedLeagues());
  }, []);

  // Use cached leagues after mount, then switch to store after hydration
  // Note: useLeagues hook already filters by organizationId, so no additional filtering needed
  const leagues = hasHydrated
    ? storeLeagues
    : (mounted && cachedLeagues.length > 0 ? cachedLeagues : storeLeagues);

  // Can create leagues when org is selected AND user is org admin (includes owner, superuser)
  const canCreate = isOrgAdmin && selectedOrgIdNum;

  function setOrgFilter(value: string | null) {
    const newParams = new URLSearchParams(searchParams);
    if (value && value !== 'all') {
      newParams.set('organization', value);
    } else {
      newParams.delete('organization');
    }
    setSearchParams(newParams);
  }

  // Render the league grid content based on state
  const renderLeagueGrid = () => {
    // If we have leagues, show them immediately
    if (leagues.length > 0) {
      return (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {leagues.map((league) => (
            <LeagueCardWrapper key={league.pk} league={league} />
          ))}
        </div>
      );
    }

    // No leagues yet - show skeleton while loading
    if (!mounted || !hasHydrated || isLoading) {
      return <LeagueGridSkeleton count={6} />;
    }

    // Hydrated but no leagues
    return <EmptyLeagues hasOrgFilter={!!selectedOrgId} />;
  };

  return (
    <div className="container mx-auto p-4">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <Trophy className="h-8 w-8 text-primary" />
          <h1 className="text-2xl font-bold">Leagues</h1>
        </div>
        {canCreate && (
          <Button onClick={() => setCreateModalOpen(true)}>
            <Plus className="w-4 h-4 mr-2" />
            Create League
          </Button>
        )}
      </div>

      {/* Organization Filter */}
      <div className="mb-6">
        <div className="w-64">
          <label className="text-sm font-medium mb-1 block">
            Filter by Organization
          </label>
          <Select
            value={selectedOrgId || 'all'}
            onValueChange={(v) => setOrgFilter(v === 'all' ? null : v)}
          >
            <SelectTrigger>
              <SelectValue placeholder="All organizations" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All organizations</SelectItem>
              {organizations
                .filter((org) => org.pk != null)
                .map((org) => (
                  <SelectItem key={org.pk} value={org.pk!.toString()}>
                    {org.name}
                  </SelectItem>
                ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {renderLeagueGrid()}

      {selectedOrgIdNum && (
        <CreateLeagueModal
          open={createModalOpen}
          onOpenChange={setCreateModalOpen}
          organizationId={selectedOrgIdNum}
        />
      )}
    </div>
  );
}
