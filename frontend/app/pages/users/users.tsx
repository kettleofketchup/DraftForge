import { Loader2, Users } from 'lucide-react';
import { memo, useEffect, useState } from 'react';
import { SearchUserDropdown } from '~/components/user/searchUser';
import type { UserClassType, UserType } from '~/components/user/types';
import { UserCard } from '~/components/user/userCard';
import { UserCreateModal } from '~/components/user/userCard/createModal';
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

/** Memoized wrapper for individual user cards */
const UserCardWrapper = memo(({
  userData,
  animationIndex,
}: {
  userData: UserType;
  animationIndex: number;
}) => {
  return (
    <UserCard
      user={userData as UserClassType}
      saveFunc={'save'}
      key={`UserCard-${userData.pk}`}
      deleteButtonType="normal"
      animationIndex={animationIndex}
    />
  );
});

/** Grid of skeleton cards for initial loading */
const UserGridSkeleton = ({ count = 8 }: { count?: number }) => (
  <div
    className="grid grid-flow-row-dense grid-auto-rows
    align-middle content-center justify-center
    grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-3 2xl:grid-cols-4
    mb-0 mt-0 p-0 bg-base-900 w-full gap-2 md:gap-4 lg:gap-6"
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

// Try to get cached users from sessionStorage (client-side only)
const getCachedUsers = (): UserType[] => {
  try {
    const stored = sessionStorage.getItem('dtx-storage');
    if (stored) {
      const parsed = JSON.parse(stored);
      return parsed?.state?.users || [];
    }
  } catch {
    // Ignore parse errors
  }
  return [];
};

export function UsersPage() {
  const currentUser = useUserStore((state) => state.currentUser);
  const getCurrentUser = useUserStore((state) => state.getCurrentUser);
  const getUsers = useUserStore((state) => state.getUsers);
  const storeUsers = useUserStore((state) => state.users);
  const hasHydrated = useUserStore((state) => state.hasHydrated);

  // Read cached users after mount to avoid hydration mismatch
  const [mounted, setMounted] = useState(false);
  const [cachedUsers, setCachedUsers] = useState<UserType[]>([]);

  useEffect(() => {
    setMounted(true);
    setCachedUsers(getCachedUsers());
  }, []);

  // Use cached users after mount, then switch to store users after hydration
  const users = hasHydrated ? storeUsers : (mounted && cachedUsers.length > 0 ? cachedUsers : storeUsers);

  const [query, setQuery] = useState('');
  const [createModalQuery, setCreateModalQuery] = useState('');
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Ensure current user is loaded
  useEffect(() => {
    if (!currentUser?.pk) {
      getCurrentUser();
    }
  }, [currentUser?.pk, getCurrentUser]);

  // Filter users - directly from store
  const filteredUsers = query === ''
    ? users
    : users.filter((person) => {
        const q = query.toLowerCase();
        return (
          person.username?.toLowerCase().includes(q) ||
          person.nickname?.toLowerCase().includes(q)
        );
      });

  // Fetch users after hydration - show cached data immediately, refresh in background
  useEffect(() => {
    if (!hasHydrated) return; // Wait for Zustand to hydrate from sessionStorage

    // If we already have users from cache, just refresh in background
    if (users.length > 0) {
      getUsers(); // Background refresh
      return;
    }

    // No cached users - fetch and wait
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
        <div
          className="grid grid-flow-row-dense grid-auto-rows
          align-middle content-center justify-center
          grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-3 2xl:grid-cols-4
          mb-0 mt-0 p-0 bg-base-900 w-full gap-2 md:gap-4 lg:gap-6"
        >
          {filteredUsers.map((u: UserType, index: number) => (
            <UserCardWrapper
              userData={u}
              key={`wrapper-${u.pk}`}
              animationIndex={index}
            />
          ))}
        </div>
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
    <>
      <div className="flex flex-col items-start p-4 h-full">
        {/* Header with search and create button - NOT affected by transitions */}
        <div
          className="grid grid-flow-row-dense grid-auto-rows
          align-middle content-center justify-center
          grid-cols-4 w-full"
        >
          <div className="flex col-span-2 w-full content-center">
            <SearchUserDropdown
              users={users}
              query={query}
              setQuery={setQuery}
            />
          </div>
          <div className="flex col-start-4 align-end content-end justify-end">
            <UserCreateModal
              query={createModalQuery}
              setQuery={setCreateModalQuery}
            />
          </div>
        </div>

        {/* User grid - affected by transitions */}
        {renderUserGrid()}
      </div>
    </>
  );
}
