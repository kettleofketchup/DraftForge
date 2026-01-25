import { Building2, ExternalLink, Pencil, Plus } from 'lucide-react';
import { useState } from 'react';
import { useParams } from 'react-router';
import { CreateLeagueModal, LeagueCard, useLeagues } from '~/components/league';
import { EditOrganizationModal, useOrganization } from '~/components/organization';
import { Button } from '~/components/ui/button';
import { useUserStore } from '~/store/userStore';

// Discord icon component
const DiscordIcon = ({ className }: { className?: string }) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 24 24"
    fill="currentColor"
    className={className}
  >
    <path d="M20.317 4.3698a19.7913 19.7913 0 00-4.8851-1.5152.0741.0741 0 00-.0785.0371c-.211.3753-.4447.8648-.6083 1.2495-1.8447-.2762-3.68-.2762-5.4868 0-.1636-.3933-.4058-.8742-.6177-1.2495a.077.077 0 00-.0785-.037 19.7363 19.7363 0 00-4.8852 1.515.0699.0699 0 00-.0321.0277C.5334 9.0458-.319 13.5799.0992 18.0578a.0824.0824 0 00.0312.0561c2.0528 1.5076 4.0413 2.4228 5.9929 3.0294a.0777.0777 0 00.0842-.0276c.4616-.6304.8731-1.2952 1.226-1.9942a.076.076 0 00-.0416-.1057c-.6528-.2476-1.2743-.5495-1.8722-.8923a.077.077 0 01-.0076-.1277c.1258-.0943.2517-.1923.3718-.2914a.0743.0743 0 01.0776-.0105c3.9278 1.7933 8.18 1.7933 12.0614 0a.0739.0739 0 01.0785.0095c.1202.099.246.1981.3728.2924a.077.077 0 01-.0066.1276 12.2986 12.2986 0 01-1.873.8914.0766.0766 0 00-.0407.1067c.3604.698.7719 1.3628 1.225 1.9932a.076.076 0 00.0842.0286c1.961-.6067 3.9495-1.5219 6.0023-3.0294a.077.077 0 00.0313-.0552c.5004-5.177-.8382-9.6739-3.5485-13.6604a.061.061 0 00-.0312-.0286zM8.02 15.3312c-1.1825 0-2.1569-1.0857-2.1569-2.419 0-1.3332.9555-2.4189 2.157-2.4189 1.2108 0 2.1757 1.0952 2.1568 2.419 0 1.3332-.9555 2.4189-2.1569 2.4189zm7.9748 0c-1.1825 0-2.1569-1.0857-2.1569-2.419 0-1.3332.9554-2.4189 2.1569-2.4189 1.2108 0 2.1757 1.0952 2.1568 2.419 0 1.3332-.946 2.4189-2.1568 2.4189Z" />
  </svg>
);

export default function OrganizationDetailPage() {
  const { organizationId } = useParams();
  const pk = organizationId ? parseInt(organizationId, 10) : undefined;
  const { organization, isLoading: orgLoading, refetch } = useOrganization(pk);
  const { leagues, isLoading: leaguesLoading } = useLeagues(pk);
  const currentUser = useUserStore((state) => state.currentUser);
  const [createLeagueOpen, setCreateLeagueOpen] = useState(false);
  const [editOrgOpen, setEditOrgOpen] = useState(false);

  const isOrgAdmin =
    currentUser?.is_superuser ||
    organization?.owner?.pk === currentUser?.pk ||
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
        {/* Organization Header */}
        <div className="card bg-base-200 shadow-lg mb-8">
          <div className="card-body">
            <div className="flex flex-col md:flex-row gap-6">
              {/* Organization Logo */}
              <div className="flex-shrink-0">
                {organization.logo ? (
                  <img
                    src={organization.logo}
                    alt={organization.name}
                    className="w-32 h-32 rounded-xl object-cover shadow-md"
                  />
                ) : (
                  <div className="w-32 h-32 rounded-xl bg-base-300 flex items-center justify-center shadow-md">
                    <Building2 className="w-16 h-16 text-muted-foreground" />
                  </div>
                )}
              </div>

              {/* Organization Info */}
              <div className="flex-1">
                <div className="flex items-start justify-between mb-2">
                  <h1 className="text-3xl font-bold">{organization.name}</h1>
                  {isOrgAdmin && (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setEditOrgOpen(true)}
                    >
                      <Pencil className="w-4 h-4 mr-2" />
                      Edit
                    </Button>
                  )}
                </div>

                {/* Discord Link */}
                {organization.discord_link && (
                  <a
                    href={organization.discord_link}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-2 text-indigo-400 hover:text-indigo-300 transition-colors mb-4"
                  >
                    <DiscordIcon className="w-5 h-5" />
                    <span>Join our Discord</span>
                    <ExternalLink className="w-4 h-4" />
                  </a>
                )}

                {/* Description */}
                {organization.description && (
                  <div className="prose prose-sm max-w-none">
                    <p className="text-base-content/80 whitespace-pre-wrap">
                      {organization.description}
                    </p>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Leagues Section */}
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

        {organization && (
          <EditOrganizationModal
            open={editOrgOpen}
            onOpenChange={setEditOrgOpen}
            organization={organization}
            onSuccess={refetch}
          />
        )}
    </div>
  );
}
