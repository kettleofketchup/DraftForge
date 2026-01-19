import { Plus, Trophy } from 'lucide-react';
import { useState } from 'react';
import { useSearchParams } from 'react-router';
import {
  CreateLeagueModal,
  LeagueCard,
  useLeagues,
} from '~/components/league';
import { useOrganizations } from '~/components/organization';
import { Button } from '~/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '~/components/ui/select';
import { useUserStore } from '~/store/userStore';

export default function LeaguesPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedOrgId = searchParams.get('organization');
  const selectedOrgIdNum = selectedOrgId ? parseInt(selectedOrgId, 10) : null;

  const { leagues, isLoading } = useLeagues(selectedOrgIdNum ?? undefined);
  const { organizations } = useOrganizations();
  const currentUser = useUserStore((state) => state.currentUser);
  const [createModalOpen, setCreateModalOpen] = useState(false);

  // Can only create leagues when an organization is selected
  const canCreate = (currentUser?.is_staff || currentUser?.is_superuser) && selectedOrgIdNum;

  function setOrgFilter(value: string | null) {
    const newParams = new URLSearchParams(searchParams);
    if (value && value !== 'all') {
      newParams.set('organization', value);
    } else {
      newParams.delete('organization');
    }
    setSearchParams(newParams);
  }

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

      {isLoading ? (
        <div className="text-center py-8 text-muted-foreground">
          Loading leagues...
        </div>
      ) : leagues.length === 0 ? (
        <div className="text-center py-8 text-muted-foreground">
          No leagues found
          {selectedOrgId && ' for this organization'}
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {leagues.map((league) => (
            <LeagueCard key={league.pk} league={league} />
          ))}
        </div>
      )}

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
