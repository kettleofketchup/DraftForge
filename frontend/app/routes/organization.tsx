import { Building2, Plus } from 'lucide-react';
import { useState } from 'react';
import { useParams } from 'react-router';
import { CreateLeagueModal, LeagueCard, useLeagues } from '~/components/league';
import { useOrganization } from '~/components/organization';
import { Button } from '~/components/ui/button';
import { useUserStore } from '~/store/userStore';

export default function OrganizationDetailPage() {
  const { organizationId } = useParams();
  const pk = organizationId ? parseInt(organizationId, 10) : undefined;
  const { organization, isLoading: orgLoading } = useOrganization(pk);
  const { leagues, isLoading: leaguesLoading } = useLeagues(pk);
  const currentUser = useUserStore((state) => state.currentUser);
  const [createLeagueOpen, setCreateLeagueOpen] = useState(false);

  const isOrgAdmin =
    currentUser?.is_superuser ||
    organization?.admins?.some((a) => a.pk === currentUser?.pk);

  if (orgLoading) {
    return (
      <div className="container mx-auto p-4 text-center">
        Loading organization...
      </div>
    );
  }

  if (!organization) {
    return (
      <div className="container mx-auto p-4 text-center">
        Organization not found
      </div>
    );
  }

  return (
    <div className="container mx-auto p-4">
      <div className="flex items-center gap-4 mb-6">
        {organization.logo ? (
          <img
            src={organization.logo}
            alt={organization.name}
            className="w-16 h-16 rounded-lg object-cover"
          />
        ) : (
          <div className="w-16 h-16 rounded-lg bg-muted flex items-center justify-center">
            <Building2 className="w-8 h-8 text-muted-foreground" />
          </div>
        )}
        <div>
          <h1 className="text-2xl font-bold">{organization.name}</h1>
          {organization.description && (
            <p className="text-muted-foreground">{organization.description}</p>
          )}
        </div>
      </div>

      <div className="flex items-center justify-between mb-4">
        <h2 className="text-xl font-semibold">Leagues</h2>
        {isOrgAdmin && (
          <Button onClick={() => setCreateLeagueOpen(true)}>
            <Plus className="w-4 h-4 mr-2" />
            Create League
          </Button>
        )}
      </div>

      {leaguesLoading ? (
        <div className="text-center py-8 text-muted-foreground">
          Loading leagues...
        </div>
      ) : leagues.length === 0 ? (
        <div className="text-center py-8 text-muted-foreground">
          No leagues found
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {leagues.map((league) => (
            <LeagueCard key={league.pk} league={league} />
          ))}
        </div>
      )}

      {pk && (
        <CreateLeagueModal
          open={createLeagueOpen}
          onOpenChange={setCreateLeagueOpen}
          organizationId={pk}
        />
      )}
    </div>
  );
}
