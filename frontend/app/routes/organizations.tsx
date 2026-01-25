import { Building2, Plus } from 'lucide-react';
import { memo, useEffect, useState } from 'react';
import {
  CreateOrganizationModal,
  OrganizationCard,
  useOrganizations,
} from '~/components/organization';
import type { OrganizationType } from '~/components/organization/schemas';
import { Button } from '~/components/ui/button';
import { Card, CardContent, CardHeader } from '~/components/ui/card';
import { useUserStore } from '~/store/userStore';

/** Skeleton loader for organization cards */
const OrganizationCardSkeleton = () => (
  <Card className="animate-pulse">
    <CardHeader className="flex flex-row items-center gap-4">
      <div className="w-12 h-12 rounded-lg bg-base-300" />
      <div className="flex-1">
        <div className="h-5 w-32 bg-base-300 rounded mb-2" />
        <div className="h-4 w-20 bg-base-300 rounded" />
      </div>
    </CardHeader>
    <CardContent>
      <div className="h-4 w-3/4 bg-base-300 rounded mb-2" />
      <div className="h-4 w-1/2 bg-base-300 rounded" />
    </CardContent>
  </Card>
);

/** Grid of skeleton cards for initial loading */
const OrganizationGridSkeleton = ({ count = 6 }: { count?: number }) => (
  <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
    {Array.from({ length: count }).map((_, index) => (
      <OrganizationCardSkeleton key={`skeleton-${index}`} />
    ))}
  </div>
);

/** Empty state when no organizations found */
const EmptyOrganizations = () => (
  <div className="flex flex-col items-center justify-center py-16 text-base-content/60">
    <Building2 className="w-16 h-16 mb-4 opacity-50" />
    <h3 className="text-xl font-semibold mb-2">No Organizations Found</h3>
    <p className="text-sm text-muted-foreground">Create a new organization to get started!</p>
  </div>
);

/** Memoized wrapper for individual organization cards */
const OrganizationCardWrapper = memo(({
  organization,
}: {
  organization: OrganizationType;
}) => {
  return <OrganizationCard organization={organization} />;
});

// Try to get cached organizations from sessionStorage (client-side only)
const getCachedOrganizations = (): OrganizationType[] => {
  try {
    const stored = sessionStorage.getItem('dtx-storage');
    if (stored) {
      const parsed = JSON.parse(stored);
      return parsed?.state?.organizations || [];
    }
  } catch {
    // Ignore parse errors
  }
  return [];
};

export default function OrganizationsPage() {
  const { organizations: storeOrganizations, isLoading } = useOrganizations();
  const currentUser = useUserStore((state) => state.currentUser);
  const hasHydrated = useUserStore((state) => state.hasHydrated);
  const [createModalOpen, setCreateModalOpen] = useState(false);

  // Read cached organizations after mount to avoid hydration mismatch
  const [mounted, setMounted] = useState(false);
  const [cachedOrganizations, setCachedOrganizations] = useState<OrganizationType[]>([]);

  useEffect(() => {
    setMounted(true);
    setCachedOrganizations(getCachedOrganizations());
  }, []);

  // Use cached organizations after mount, then switch to store after hydration
  const organizations = hasHydrated
    ? storeOrganizations
    : (mounted && cachedOrganizations.length > 0 ? cachedOrganizations : storeOrganizations);

  // Render the organization grid content based on state
  const renderOrganizationGrid = () => {
    // If we have organizations, show them immediately
    if (organizations.length > 0) {
      return (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {organizations.map((org) => (
            <OrganizationCardWrapper key={org.pk} organization={org} />
          ))}
        </div>
      );
    }

    // No organizations yet - show skeleton while loading
    if (!mounted || !hasHydrated || isLoading) {
      return <OrganizationGridSkeleton count={6} />;
    }

    // Hydrated but no organizations
    return <EmptyOrganizations />;
  };

  return (
    <div className="container mx-auto p-4">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <Building2 className="h-8 w-8 text-primary" />
            <h1 className="text-2xl font-bold">Organizations</h1>
          </div>
          {currentUser?.is_superuser && (
            <Button onClick={() => setCreateModalOpen(true)}>
              <Plus className="w-4 h-4 mr-2" />
              Create Organization
            </Button>
          )}
        </div>

        {renderOrganizationGrid()}

        <CreateOrganizationModal
          open={createModalOpen}
          onOpenChange={setCreateModalOpen}
        />
    </div>
  );
}
