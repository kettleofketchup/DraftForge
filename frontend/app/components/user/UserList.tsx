/**
 * UserList - Performant user list with progressive rendering
 *
 * Renders users in batches to avoid blocking the main thread.
 * Used by /users page and organization Users tab.
 */

import { Loader2, Search, Users, X } from 'lucide-react';
import { memo, useEffect, useMemo, useState } from 'react';
import { Input } from '~/components/ui/input';
import type { UserClassType, UserType } from '~/components/user/types';
import { UserCard } from '~/components/user/userCard';
import { useDebouncedValue } from '~/hooks/useDebouncedValue';

/** Hook for progressive/batched rendering of items */
export const useProgressiveRender = <T,>(
  items: T[],
  batchSize = 12,
  delay = 50
) => {
  const [visibleCount, setVisibleCount] = useState(batchSize);

  useEffect(() => {
    // Only reset progressive loading when the list grows beyond what we've shown.
    // Shrinking (e.g. removing a user) should NOT reset — just let the remaining
    // items stay visible so the removed card disappears without a full re-render.
    if (items.length > visibleCount) {
      setVisibleCount(batchSize);
    }
  }, [items.length, batchSize]);

  useEffect(() => {
    if (visibleCount >= items.length) return;

    const timer = setTimeout(() => {
      setVisibleCount((prev) => Math.min(prev + batchSize, items.length));
    }, delay);

    return () => clearTimeout(timer);
  }, [visibleCount, items.length, batchSize, delay]);

  return {
    visibleItems: items.slice(0, visibleCount),
    isLoading: visibleCount < items.length,
    progress: items.length > 0 ? visibleCount / items.length : 1,
  };
};

/** Skeleton loader for user cards */
export const UserCardSkeleton = () => (
  <div className="flex w-full sm:gap-2 md:gap-4 py-4 justify-center content-center">
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
const UserCardWrapper = memo(
  ({
    userData,
    animationIndex,
    compact,
    deleteButtonType,
    organizationId,
    leagueId,
  }: {
    userData: UserType;
    animationIndex: number;
    compact?: boolean;
    deleteButtonType?: 'normal' | 'tournament';
    organizationId?: number;
    leagueId?: number;
  }) => {
    return (
      <UserCard
        user={userData as UserClassType}
        saveFunc={'save'}
        key={`UserCard-${userData.pk}`}
        deleteButtonType={deleteButtonType ?? 'normal'}
        animationIndex={animationIndex}
        compact={compact}
        organizationId={organizationId}
        leagueId={leagueId}
      />
    );
  }
);

/** Grid of skeleton cards for initial loading */
export const UserGridSkeleton = ({ count = 12 }: { count?: number }) => (
  <div
    className="grid grid-flow-row-dense grid-auto-rows
    align-middle content-center justify-center
    grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4
    mb-0 mt-0 p-0 w-full gap-2 md:gap-3 lg:gap-4"
  >
    {Array.from({ length: count }).map((_, index) => (
      <UserCardSkeleton key={`skeleton-${index}`} />
    ))}
  </div>
);

/** Empty state when no users found */
export const EmptyUsers = ({ message = 'No members found' }: { message?: string }) => (
  <div className="flex flex-col items-center justify-center py-16 text-base-content/60">
    <Users className="w-16 h-16 mb-4 opacity-50" />
    <h3 className="text-xl font-semibold mb-2">{message}</h3>
  </div>
);

interface UserListProps {
  /** Users to display */
  users: UserType[];
  /** Whether data is loading */
  isLoading?: boolean;
  /** Batch size for progressive rendering */
  batchSize?: number;
  /** Delay between batches in ms */
  batchDelay?: number;
  /** Optional search query for filtering (controlled from parent) */
  searchQuery?: string;
  /** Show built-in search input */
  showSearch?: boolean;
  /** Placeholder text for search input */
  searchPlaceholder?: string;
  /** Empty state message */
  emptyMessage?: string;
  /** Grid columns configuration */
  gridCols?: string;
  /** Compact card display */
  compact?: boolean;
  /** Delete button type for cards */
  deleteButtonType?: 'normal' | 'tournament';
  /** Organization ID for scoped MMR display */
  organizationId?: number;
  /** League ID for scoped MMR display */
  leagueId?: number;
}

/**
 * Performant user list with progressive rendering.
 * Renders users in batches to avoid blocking the main thread.
 */
export function UserList({
  users,
  isLoading = false,
  batchSize = 12,
  batchDelay = 100,
  searchQuery: externalSearchQuery = '',
  showSearch = false,
  searchPlaceholder = 'Search by name...',
  emptyMessage = 'No members found',
  gridCols = 'grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4',
  compact,
  deleteButtonType,
  organizationId,
  leagueId,
}: UserListProps) {
  // Internal search state (used when showSearch is true)
  const [internalQuery, setInternalQuery] = useState('');

  // Use external query if provided, otherwise use internal
  const searchQuery = externalSearchQuery || internalQuery;
  const debouncedQuery = useDebouncedValue(searchQuery, 300);

  // Filter users with debounced query
  const filteredUsers = useMemo(() => {
    if (debouncedQuery === '') return users;
    const q = debouncedQuery.toLowerCase();
    return users.filter(
      (person) =>
        person.username?.toLowerCase().includes(q) ||
        person.nickname?.toLowerCase().includes(q)
    );
  }, [users, debouncedQuery]);

  // Progressive render for performance
  const { visibleItems, isLoading: isProgressiveLoading } = useProgressiveRender(
    filteredUsers,
    batchSize,
    batchDelay
  );

  // Loading state - show skeleton
  if (isLoading && users.length === 0) {
    return <UserGridSkeleton count={8} />;
  }

  // Empty state
  if (users.length === 0) {
    return <EmptyUsers message={emptyMessage} />;
  }

  // No results from filter
  if (filteredUsers.length === 0) {
    return (
      <>
        {showSearch && (
          <div className="relative mb-4">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              type="text"
              placeholder={searchPlaceholder}
              value={internalQuery}
              onChange={(e) => setInternalQuery(e.target.value)}
              className="pl-9 pr-9"
            />
            {internalQuery && (
              <button
                type="button"
                onClick={() => setInternalQuery('')}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              >
                <X className="h-4 w-4" />
              </button>
            )}
          </div>
        )}
        <EmptyUsers message="No matching users found" />
      </>
    );
  }

  return (
    <>
      {showSearch && (
        <div className="relative mb-4">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            type="text"
            placeholder={searchPlaceholder}
            value={internalQuery}
            onChange={(e) => setInternalQuery(e.target.value)}
            className="pl-9 pr-9"
          />
          {internalQuery && (
            <button
              type="button"
              onClick={() => setInternalQuery('')}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
            >
              <X className="h-4 w-4" />
            </button>
          )}
        </div>
      )}
      <div
        className={`grid grid-flow-row-dense grid-auto-rows
        align-middle content-center justify-center
        ${gridCols}
        mb-0 mt-0 p-0 w-full gap-2 md:gap-3 lg:gap-4`}
      >
        {visibleItems.map((u: UserType, index: number) => (
          <UserCardWrapper
            userData={u}
            key={`wrapper-${u.pk}`}
            animationIndex={index}
            compact={compact}
            deleteButtonType={deleteButtonType}
            organizationId={organizationId}
            leagueId={leagueId}
          />
        ))}
      </div>
      {isProgressiveLoading && (
        <div className="flex items-center justify-center py-4 text-muted-foreground">
          <Loader2 className="w-4 h-4 animate-spin mr-2" />
          <span className="text-sm">Loading more users...</span>
        </div>
      )}
    </>
  );
}
