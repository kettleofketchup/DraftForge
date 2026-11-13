import { Search, X } from 'lucide-react';
import { useEffect, useId, useState } from 'react';
import { useSearchParams } from 'react-router';
import { useLeagues } from '~/components/league';
import { useOrganizations } from '~/components/organization';
import {
  ORG_SCOPE_ALL,
  ORG_SCOPE_MINE,
  groupOrganizations,
  isDefaultOrgScope,
  isExplicitOrgScope,
  orgScopeParam,
  orgScopeValue,
  parseOrgScope,
} from '~/components/tournament/orgScope';
import { filtersActive, parseFilterId } from '~/components/tournament/tournamentBuckets';
import {
  BrandSelect,
  BrandSelectContent,
  BrandSelectItem,
  BrandSelectTrigger,
  SelectGroup,
  SelectLabel,
  SelectValue,
} from '~/components/ui/brand-select';
import { SecondaryButton } from '~/components/ui/buttons';
import { Input } from '~/components/ui/input';
import { Label } from '~/components/ui/label';
import { Skeleton } from '~/components/ui/skeleton';

type FilterKey = 'organization' | 'league';

const ALL = 'all';

export function nextFilterParams(
  params: URLSearchParams,
  key: FilterKey,
  value: string,
  isLoggedIn = false,
): URLSearchParams {
  const next = new URLSearchParams(params);
  const param =
    key === 'organization' ? orgScopeParam(value, isLoggedIn) : value === ALL ? null : value;
  if (param === null) {
    next.delete(key);
  } else {
    next.set(key, param);
  }
  if (key === 'organization') {
    next.delete('league');
  }
  return next;
}

function selectValue(
  id: number | undefined,
  known: ReadonlyArray<{ pk?: number | null }>,
): string {
  if (id === undefined) return ALL;
  return known.some((item) => item.pk === id) ? String(id) : '';
}

const GROUP_LABEL = 'px-2 py-1.5 text-xs font-semibold text-muted-foreground';

interface TournamentFilterBarProps {
  searchInput: string;
  onSearchInputChange: (value: string) => void;
  isLoggedIn: boolean;
  memberOrgIds: number[] | undefined;
  membershipPending: boolean;
}

export function TournamentFilterBar({
  searchInput,
  onSearchInputChange,
  isLoggedIn,
  memberOrgIds,
  membershipPending,
}: TournamentFilterBarProps) {
  const [mounted, setMounted] = useState(false);
  const [searchParams, setSearchParams] = useSearchParams();
  const orgLabelId = useId();
  const orgValueId = useId();
  const leagueLabelId = useId();
  const leagueValueId = useId();

  useEffect(() => {
    setMounted(true);
  }, []);

  const rawOrganization = searchParams.get('organization');
  const scope = parseOrgScope(rawOrganization, isLoggedIn);
  const scopePending = membershipPending && !isExplicitOrgScope(rawOrganization);
  const organization = scope.kind === 'org' ? scope.id : undefined;
  const league = parseFilterId(searchParams.get('league'));

  const { organizations, isLoading: orgsLoading } = useOrganizations();
  const { leagues, isLoading: leaguesLoading } = useLeagues(organization);
  const { yours, others } = groupOrganizations(
    organizations,
    isLoggedIn ? memberOrgIds : undefined,
  );

  const active = filtersActive({
    scopeChanged: !scopePending && !isDefaultOrgScope(scope, isLoggedIn),
    league,
    searchInput,
  });
  const orgValue =
    scope.kind === 'org' ? selectValue(scope.id, organizations) : orgScopeValue(scope);

  const setFilter = (key: FilterKey, value: string) => {
    setSearchParams(nextFilterParams(searchParams, key, value, isLoggedIn));
  };

  const clearFilters = () => {
    const next = new URLSearchParams(searchParams);
    next.delete('organization');
    next.delete('league');
    setSearchParams(next);
    onSearchInputChange('');
  };

  const searchBox = (
    <div className="relative w-full sm:max-w-sm">
      <Search
        className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground"
        aria-hidden
      />
      <Input
        type="text"
        aria-label="Search tournaments"
        placeholder="Search tournaments"
        data-testid="tournaments-search"
        className="pl-9"
        value={searchInput}
        onChange={(e) => onSearchInputChange(e.target.value)}
      />
    </div>
  );

  if (!mounted) {
    return (
      <div className="flex w-full flex-wrap items-end gap-2">
        {searchBox}
        <div className="flex w-full flex-col gap-1 sm:w-48">
          <Label className="text-xs text-muted-foreground">Organization</Label>
          <Skeleton className="h-9 w-full sm:w-48" />
        </div>
        <div className="flex w-full flex-col gap-1 sm:w-48">
          <Label className="text-xs text-muted-foreground">League</Label>
          <Skeleton className="h-9 w-full sm:w-48" />
        </div>
      </div>
    );
  }

  return (
    <div className="flex w-full flex-wrap items-end gap-2">
      {searchBox}
      <div className="flex w-full flex-col gap-1 sm:w-48">
        <Label id={orgLabelId} className="text-xs text-muted-foreground">
          Organization
        </Label>
        {scopePending ? (
          <Skeleton
            data-testid="tournaments-filter-organization-pending"
            className="h-9 w-full sm:w-48"
          />
        ) : (
          <BrandSelect
            value={orgValue}
            onValueChange={(v) => setFilter('organization', v)}
          >
            <BrandSelectTrigger
              aria-labelledby={`${orgLabelId} ${orgValueId}`}
              data-testid="tournaments-filter-organization"
              className="w-full min-w-0 max-w-full sm:w-48"
            >
              <SelectValue
                id={orgValueId}
                placeholder={orgsLoading ? 'Loading organizations…' : 'Unknown organization'}
              />
            </BrandSelectTrigger>
            <BrandSelectContent>
              {isLoggedIn && (
                <BrandSelectItem value={ORG_SCOPE_MINE}>My organizations</BrandSelectItem>
              )}
              <BrandSelectItem value={ORG_SCOPE_ALL}>All organizations</BrandSelectItem>
              {isLoggedIn && yours.length > 0 ? (
                <>
                  <SelectGroup>
                    <SelectLabel className={GROUP_LABEL}>Your organizations</SelectLabel>
                    {yours.map((org) => (
                      <BrandSelectItem key={org.pk} value={String(org.pk)}>
                        {org.name}
                      </BrandSelectItem>
                    ))}
                  </SelectGroup>
                  {others.length > 0 && (
                    <SelectGroup>
                      <SelectLabel className={GROUP_LABEL}>Other organizations</SelectLabel>
                      {others.map((org) => (
                        <BrandSelectItem key={org.pk} value={String(org.pk)}>
                          {org.name}
                        </BrandSelectItem>
                      ))}
                    </SelectGroup>
                  )}
                </>
              ) : (
                others.map((org) => (
                  <BrandSelectItem key={org.pk} value={String(org.pk)}>
                    {org.name}
                  </BrandSelectItem>
                ))
              )}
            </BrandSelectContent>
          </BrandSelect>
        )}
      </div>
      <div className="flex w-full flex-col gap-1 sm:w-48">
        <Label id={leagueLabelId} className="text-xs text-muted-foreground">
          League
        </Label>
        <BrandSelect
          value={selectValue(league, leagues)}
          onValueChange={(v) => setFilter('league', v)}
        >
          <BrandSelectTrigger
            aria-labelledby={`${leagueLabelId} ${leagueValueId}`}
            data-testid="tournaments-filter-league"
            className="w-full min-w-0 max-w-full sm:w-48"
          >
            <SelectValue
              id={leagueValueId}
              placeholder={leaguesLoading ? 'Loading leagues…' : 'Unknown league'}
            />
          </BrandSelectTrigger>
          <BrandSelectContent>
            <BrandSelectItem value={ALL}>All leagues</BrandSelectItem>
            {leagues
              .filter((l) => l.pk != null)
              .map((l) => (
                <BrandSelectItem key={l.pk} value={String(l.pk)}>
                  {l.name}
                </BrandSelectItem>
              ))}
          </BrandSelectContent>
        </BrandSelect>
      </div>
      {active && (
        <SecondaryButton data-testid="tournaments-filter-clear" onClick={clearFilters}>
          <X className="size-4" aria-hidden />
          Clear filters
        </SecondaryButton>
      )}
    </div>
  );
}
