import type { ReactNode } from 'react';

import {
  Command,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from '~/components/ui/command';
import type { UserSearchStatus } from '~/hooks/useUserSearch';
import { userRefPk } from '~/lib/userDisplayName';
import { USER_SEARCH_MIN_LENGTH, type SearchableUser } from '~/lib/userSearch';
import { cn } from '~/lib/utils';

import { UserSearchOption } from './UserSearchOption';

export interface UserPickerGroup<T> {
  heading?: string;
  users: T[];
}

export interface UserPickerTestIds<T> {
  input?: string;
  results?: string;
  option?: (user: T) => string;
  hint?: string;
  searching?: string;
  empty?: string;
  error?: string;
}

export interface UserPickerProps<T extends SearchableUser> {
  query: string;
  onQueryChange: (query: string) => void;
  /** Already-filtered results; pass `groups` instead for headed sections. */
  results?: T[];
  groups?: UserPickerGroup<T>[];
  /** From `useUserSearch`; omit for client-side lists filtered with `filterUsers`. */
  status?: UserSearchStatus;
  onSelect: (user: T) => void;
  isDisabled?: (user: T) => boolean;
  renderBadge?: (user: T) => ReactNode;
  /** Defaults to the user's pk; Discord members need their Discord id. */
  getKey?: (user: T) => string | number;
  placeholder?: string;
  ariaLabel?: string;
  emptyMessage?: string;
  errorMessage?: string;
  /** Rows rendered at most; client-side lists can hold a whole org. */
  limit?: number;
  footer?: ReactNode;
  autoFocus?: boolean;
  className?: string;
  listClassName?: string;
  testIds?: UserPickerTestIds<T>;
}

function Status({
  children,
  testId,
}: {
  children: ReactNode;
  testId?: string;
}) {
  return (
    <p
      className="px-3 py-4 text-center text-sm text-muted-foreground"
      data-testid={testId}
    >
      {children}
    </p>
  );
}

/** Search box plus result list for picking a person. Wrap it in a Popover or Dialog as needed. */
export function UserPicker<T extends SearchableUser>({
  query,
  onQueryChange,
  results,
  groups,
  status,
  onSelect,
  isDisabled,
  renderBadge,
  getKey = (user) => userRefPk(user) ?? JSON.stringify(user),
  placeholder = 'Search users…',
  ariaLabel = 'Search users',
  emptyMessage = 'No users found',
  errorMessage = 'Search failed',
  limit = 50,
  footer,
  autoFocus,
  className,
  listClassName,
  testIds = {},
}: UserPickerProps<T>) {
  const sections: UserPickerGroup<T>[] = groups ?? [{ users: results ?? [] }];
  const total = sections.reduce((n, g) => n + g.users.length, 0);
  let remaining = limit;
  const shown = sections.map((g) => {
    const users = g.users.slice(0, Math.max(remaining, 0));
    remaining -= users.length;
    return { ...g, users };
  });

  let body: ReactNode;
  if (status === 'too-short') {
    body = (
      <Status testId={testIds.hint}>
        Type at least {USER_SEARCH_MIN_LENGTH} characters to search.
      </Status>
    );
  } else if (status === 'error') {
    body = <Status testId={testIds.error}>{errorMessage}</Status>;
  } else if (status === 'searching' && total === 0) {
    body = <Status testId={testIds.searching}>Searching…</Status>;
  } else if (total === 0) {
    body = <Status testId={testIds.empty}>{emptyMessage}</Status>;
  } else {
    body = (
      <>
        {shown.map((group, i) =>
          group.users.length ? (
            <CommandGroup key={group.heading ?? i} heading={group.heading}>
              {group.users.map((user) => {
                const key = String(getKey(user));
                return (
                  <CommandItem
                    key={key}
                    value={key}
                    disabled={isDisabled?.(user)}
                    onSelect={() => onSelect(user)}
                    data-testid={testIds.option?.(user)}
                    className="min-h-11 sm:min-h-9"
                  >
                    <UserSearchOption user={user} badge={renderBadge?.(user)} />
                  </CommandItem>
                );
              })}
            </CommandGroup>
          ) : null,
        )}
        {status === 'searching' ? (
          <Status testId={testIds.searching}>Searching…</Status>
        ) : null}
        {total > limit ? (
          <Status>
            Showing {limit} of {total}. Keep typing to narrow it down.
          </Status>
        ) : null}
      </>
    );
  }

  return (
    <Command shouldFilter={false} className={className}>
      <CommandInput
        value={query}
        onValueChange={onQueryChange}
        placeholder={placeholder}
        aria-label={ariaLabel}
        autoFocus={autoFocus}
        autoComplete="off"
        data-testid={testIds.input}
      />
      <CommandList className={cn(listClassName)} data-testid={testIds.results}>
        {body}
      </CommandList>
      {footer}
    </Command>
  );
}
