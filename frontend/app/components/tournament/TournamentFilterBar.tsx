import { ChevronDown, Filter, X } from 'lucide-react';
import { useState } from 'react';
import { useSearchParams } from 'react-router';
import { useLeagues } from '~/components/league';
import { useOrganizations } from '~/components/organization';
import { Button } from '~/components/ui/button';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '~/components/ui/collapsible';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '~/components/ui/select';

export function TournamentFilterBar() {
  const [open, setOpen] = useState(false);
  const [searchParams, setSearchParams] = useSearchParams();
  const { organizations } = useOrganizations();

  const selectedOrgId = searchParams.get('organization');
  const selectedLeagueId = searchParams.get('league');

  const { leagues } = useLeagues(
    selectedOrgId ? parseInt(selectedOrgId, 10) : undefined,
  );

  const hasFilters = selectedOrgId || selectedLeagueId;

  function setFilter(key: string, value: string | null) {
    const newParams = new URLSearchParams(searchParams);
    if (value) {
      newParams.set(key, value);
    } else {
      newParams.delete(key);
    }
    // Clear league if org changes
    if (key === 'organization') {
      newParams.delete('league');
    }
    setSearchParams(newParams);
  }

  function clearFilters() {
    setSearchParams(new URLSearchParams());
  }

  return (
    <Collapsible open={open} onOpenChange={setOpen} className="mb-4">
      <div className="flex items-center gap-2">
        <CollapsibleTrigger asChild>
          <Button variant="outline" size="sm">
            <Filter className="w-4 h-4 mr-2" />
            Filter
            <ChevronDown
              className={`w-4 h-4 ml-2 transition-transform ${open ? 'rotate-180' : ''}`}
            />
          </Button>
        </CollapsibleTrigger>
        {hasFilters && (
          <Button variant="ghost" size="sm" onClick={clearFilters}>
            <X className="w-4 h-4 mr-1" />
            Clear filters
          </Button>
        )}
      </div>

      <CollapsibleContent className="mt-4">
        <div className="flex flex-wrap gap-4">
          <div className="w-48">
            <label className="text-sm font-medium mb-1 block">
              Organization
            </label>
            <Select
              value={selectedOrgId || 'all'}
              onValueChange={(v) => setFilter('organization', v === 'all' ? null : v)}
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

          {selectedOrgId && (
            <div className="w-48">
              <label className="text-sm font-medium mb-1 block">League</label>
              <Select
                value={selectedLeagueId || 'all'}
                onValueChange={(v) => setFilter('league', v === 'all' ? null : v)}
              >
                <SelectTrigger>
                  <SelectValue placeholder="All leagues" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All leagues</SelectItem>
                  {leagues
                    .filter((league) => league.pk != null)
                    .map((league) => (
                      <SelectItem key={league.pk} value={league.pk!.toString()}>
                        {league.name}
                      </SelectItem>
                    ))}
                </SelectContent>
              </Select>
            </div>
          )}
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}
