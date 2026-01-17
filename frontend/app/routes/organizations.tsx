import { Plus } from 'lucide-react';
import { useState } from 'react';
import {
  CreateOrganizationModal,
  OrganizationCard,
  useOrganizations,
} from '~/components/organization';
import { Button } from '~/components/ui/button';
import { useUserStore } from '~/store/userStore';

export default function OrganizationsPage() {
  const { organizations, isLoading } = useOrganizations();
  const currentUser = useUserStore((state) => state.currentUser);
  const [createModalOpen, setCreateModalOpen] = useState(false);

  return (
    <div className="container mx-auto p-4">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">Organizations</h1>
        {currentUser?.is_superuser && (
          <Button onClick={() => setCreateModalOpen(true)}>
            <Plus className="w-4 h-4 mr-2" />
            Create Organization
          </Button>
        )}
      </div>

      {isLoading ? (
        <div className="text-center py-8 text-muted-foreground">
          Loading organizations...
        </div>
      ) : organizations.length === 0 ? (
        <div className="text-center py-8 text-muted-foreground">
          No organizations found
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {organizations.map((org) => (
            <OrganizationCard key={org.pk} organization={org} />
          ))}
        </div>
      )}

      <CreateOrganizationModal
        open={createModalOpen}
        onOpenChange={setCreateModalOpen}
      />
    </div>
  );
}
