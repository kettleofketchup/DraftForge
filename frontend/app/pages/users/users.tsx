import { Loader2, Users } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { SearchUserDropdown } from '~/components/user/searchUser';
import type { UserType } from '~/components/user/types';
import { VirtualizedUserGrid } from '~/components/user/VirtualizedUserGrid';
import { useDebouncedValue } from '~/hooks/useDebouncedValue';
import { useResolvedUsers } from '~/hooks/useResolvedUsers';
import { useUserStore } from '~/store/userStore';

/** Skeleton loader for user cards */
const UserCardSkeleton = () => (
  <div
    className="flex w-full sm:gap-2 md:gap-4 py-4 justify-center content-center"
  >
    <div className="justify-between p-2 h-full card bg-base-200 shadow-md w-full max-w-sm animate-pulse">
      {/* Top bar skeleton - avatar + header */}
      <div className="flex items-center gap-2 justify-start">
        <div className="w-16 h-16 rounded-full bg-base-300" />
        <div className="flex-1">
          <div className="h-5 w-32 bg-base-300 rounded mb-2" />
          <div className="flex gap-2">
            <div className="h-4 w-12 bg-base-300 rounded" />
          </div>
        </div>
      </div>
      {/* Content skeleton */}
      <div className="mt-2 space-y-2 text-sm">
        <div className="h-4 w-3/4 bg-base-300 rounded" />
        <div className="h-4 w-1/2 bg-base-300 rounded" />
        <div className="h-4 w-2/3 bg-base-300 rounded" />
        <div className="flex gap-2 mt-2">
          <div className="h-6 w-6 bg-base-300 rounded" />
          <div className="h-6 w-6 bg-base-300 rounded" />
          <div className="h-6 w-6 bg-base-300 rounded" />
        </div>
      </div>
      {/* Loading indicator */}
      <div className="flex items-center justify-center mt-4 text-base-content/50">
        <Loader2 className="w-4 h-4 animate-spin mr-2" />
        <span className="text-sm">Loading...</span>
      </div>
    </div>
  </div>
);

/** Grid of skeleton cards for initial loading */
const UserGridSkeleton = ({ count = 12 }: { count?: number }) => (
  <div
    className="grid grid-flow-row-dense grid-auto-rows
    align-middle content-center justify-center
    grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5
    mb-0 mt-0 p-0 bg-background w-full gap-6 md:gap-8 lg:gap-10"
  >
    {Array.from({ length: count }).map((_, index) => (
      <UserCardSkeleton key={`skeleton-${index}`} />
    ))}
  </div>
);

/** Empty state when no users found */
const EmptyUsers = () => (
  <div className="flex flex-col items-center justify-center py-16 text-base-content/60">
    <Users className="w-16 h-16 mb-4 opacity-50" />
    <h3 className="text-xl font-semibold mb-2">No Users Found</h3>
    <p className="text-sm">Create a new user to get started!</p>
  </div>
);

export function UsersPage() {
  const currentUser = useUserStore((state) => state.currentUser);
  const getCurrentUser = useUserStore((state) => state.getCurrentUser);
  const getUsers = useUserStore((state) => state.getUsers);
  const globalUserPks = useUserStore((state) => state.globalUserPks);
  const users = useResolvedUsers(globalUserPks);
  const hasHydrated = useUserStore((state) => state.hasHydrated);

  const [query, setQuery] = useState('');
  const debouncedQuery = useDebouncedValue(query, 300);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Ensure current user is loaded
  useEffect(() => {
    if (!currentUser?.pk) {
      getCurrentUser();
    }
  }, [currentUser?.pk, getCurrentUser]);

  // Filter users with debounced query - memoized for performance
  const filteredUsers = useMemo(() => {
    if (debouncedQuery === '') return users;
    const q = debouncedQuery.toLowerCase();
    return users.filter((person) =>
      person.username?.toLowerCase().includes(q) ||
      person.nickname?.toLowerCase().includes(q)
    );
  }, [users, debouncedQuery]);

  // Fetch users after hydration
  useEffect(() => {
    if (!hasHydrated) return;

    if (globalUserPks.length > 0) {
      getUsers(); // Background refresh
      return;
    }

    // No users yet - fetch and wait
    const fetchUsers = async () => {
      setIsRefreshing(true);
      setError(null);
      try {
        await getUsers();
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load users');
      } finally {
        setIsRefreshing(false);
      }
    };
    fetchUsers();
  }, [hasHydrated]);

  if (error) {
    return (
      <div className="flex justify-center align-middle content-center pt-10 text-red-500">
        Error: {error}
      </div>
    );
  }

  // Render the user grid content based on state
  const renderUserGrid = () => {
    // If we have users, show them immediately (no waiting)
    if (users.length > 0) {
      if (filteredUsers.length === 0) {
        return <EmptyUsers />;
      }

      return (
        <VirtualizedUserGrid
          users={filteredUsers}
          cols={{ base: 1, sm: 2, md: 3, lg: 3, xl: 4, '2xl': 5 }}
        />
      );
    }

    // No users yet - show skeleton while loading
    if (!hasHydrated || isRefreshing) {
      return <UserGridSkeleton count={8} />;
    }

    // Hydrated but no users
    return <EmptyUsers />;
  };

  return (
    <div className="flex flex-col items-start p-4">
      {/* Sticky header — title + search pin to the top of the scroll
          viewport (Radix ScrollArea inside root.tsx) so the search field
          stays accessible while scrolling through the user grid below.
          bg-background covers cards scrolling underneath. */}
      <div className="sticky top-0 z-20 bg-background w-full pb-3 -mx-4 px-4">
        <div className="flex items-center gap-2 mb-3 w-full">
          <Users className="w-6 h-6 text-primary" />
          <h1 className="text-xl font-semibold">Users</h1>
          <span className="text-sm text-muted-foreground">
            {debouncedQuery ? (
              <>
                {filteredUsers.length} of {users.length}
              </>
            ) : (
              <>{users.length} total</>
            )}
          </span>
        </div>

        <div className="w-full">
          <SearchUserDropdown
            users={users}
            query={query}
            setQuery={setQuery}
          />
        </div>
      </div>

      {/* User grid - affected by transitions */}
      {renderUserGrid()}
    </div>
  );
}
