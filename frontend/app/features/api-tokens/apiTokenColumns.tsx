import { formatDistanceToNow } from 'date-fns';

import { Badge } from '~/components/ui/badge';
import { SecondaryButton } from '~/components/ui/buttons';
import {
  DataTableColumnHeader,
  type AppColumnDef,
} from '~/components/ui/data-table';
import { UserAvatar } from '~/components/user/UserAvatar';
import { DisplayName } from '~/components/user/avatar';
import { cn } from '~/lib/utils';
import { operationLabel, type ApiToken } from './schemas';

export type ApiTokenColumnId =
  | 'name'
  | 'prefix'
  | 'owner'
  | 'created'
  | 'last_used'
  | 'status'
  | 'actions';

export const DEFAULT_API_TOKEN_COLUMNS: readonly ApiTokenColumnId[] = [
  'name',
  'prefix',
  'owner',
  'created',
  'last_used',
  'status',
  'actions',
];

export function maskedToken(prefix: string): string {
  return `dfk_${prefix}_…`;
}

export function relativeTime(iso: string | null): string {
  return iso
    ? formatDistanceToNow(new Date(iso), { addSuffix: true })
    : 'Never';
}

/** A token's granted operations, by their human labels. */
function OperationList({
  operations,
  className,
  'data-testid': testId,
}: {
  operations: string[];
  className?: string;
  'data-testid'?: string;
}) {
  return (
    <ul
      className={cn(
        'flex flex-col gap-0.5 text-xs text-muted-foreground',
        className,
      )}
      aria-label="Granted operations"
      data-testid={testId}
    >
      {operations.map((op) => (
        <li key={op} className="break-words" title={op}>
          {operationLabel(op)}
        </li>
      ))}
    </ul>
  );
}

function TokenStatus({
  token: t,
  'data-testid': testId,
}: {
  token: ApiToken;
  'data-testid': string;
}) {
  return t.revoked_at ? (
    <Badge
      variant="outline"
      title={
        t.revoked_by ? `Revoked by ${DisplayName(t.revoked_by)}` : undefined
      }
      data-testid={testId}
    >
      Revoked
    </Badge>
  ) : (
    <Badge variant="secondary" data-testid={testId}>
      Active
    </Badge>
  );
}

const time = (iso: string | null): number =>
  iso ? new Date(iso).getTime() : 0;

export interface MakeApiTokenColumnsOptions {
  testIdPrefix: string;
  columns?: readonly ApiTokenColumnId[];
  canRevoke?: (token: ApiToken) => boolean;
  onRevoke?: (token: ApiToken) => void;
  revoking?: boolean;
}

export function makeApiTokenColumns({
  testIdPrefix,
  columns = DEFAULT_API_TOKEN_COLUMNS,
  canRevoke = () => true,
  onRevoke,
  revoking = false,
}: MakeApiTokenColumnsOptions): AppColumnDef<ApiToken>[] {
  const all: Record<ApiTokenColumnId, AppColumnDef<ApiToken> | null> = {
    name: {
      id: 'name',
      accessorKey: 'name',
      header: ({ column }) => (
        <DataTableColumnHeader column={column} title="Name" />
      ),
      cell: ({ row }) => {
        const t = row.original;
        return (
          <div className="flex min-w-0 flex-col gap-0.5">
            <span
              className="break-words font-medium"
              data-testid={`${testIdPrefix}-name-${t.id}`}
            >
              {t.name}
            </span>
            <span className="font-mono text-xs break-all text-muted-foreground sm:hidden">
              {maskedToken(t.prefix)}
            </span>
            <span className="text-xs text-muted-foreground md:hidden">
              {t.user ? DisplayName(t.user) : 'Deleted user'} · last used{' '}
              {relativeTime(t.last_used_at).toLowerCase()}
            </span>
            <OperationList operations={t.operations} className="sm:hidden" />
            {/* On phones the status sits here so the name keeps its width. */}
            <span className="mt-1 sm:hidden">
              <TokenStatus
                token={t}
                data-testid={`${testIdPrefix}-status-mobile-${t.id}`}
              />
            </span>
          </div>
        );
      },
      meta: {
        headClassName: 'min-w-36 pr-4',
        cellClassName: 'min-w-36',
      },
    },
    prefix: {
      id: 'prefix',
      accessorKey: 'prefix',
      enableSorting: false,
      header: 'Token',
      cell: ({ row }) => (
        <div className="flex flex-col gap-1">
          <code
            className="font-mono text-xs"
            data-testid={`${testIdPrefix}-prefix-${row.original.id}`}
          >
            {maskedToken(row.original.prefix)}
          </code>
          <span
            className="text-xs text-muted-foreground"
            data-testid={`${testIdPrefix}-created-${row.original.id}`}
          >
            Created {relativeTime(row.original.created_at).toLowerCase()}
          </span>
          <OperationList
            operations={row.original.operations}
            data-testid={`${testIdPrefix}-operations-${row.original.id}`}
          />
        </div>
      ),
      meta: {
        headClassName: 'hidden w-44 sm:table-cell',
        cellClassName: 'hidden w-44 sm:table-cell',
      },
    },
    owner: {
      id: 'owner',
      accessorFn: (t) => (t.user ? DisplayName(t.user) : ''),
      enableSorting: false,
      header: 'Owner',
      cell: ({ row }) => {
        const user = row.original.user;
        if (!user) {
          return <span className="text-muted-foreground">Deleted user</span>;
        }
        return (
          <span className="flex min-w-0 items-center gap-2">
            <UserAvatar user={user} size="xs" />
            <span className="truncate">{DisplayName(user)}</span>
          </span>
        );
      },
      meta: {
        headClassName: 'hidden w-40 md:table-cell',
        cellClassName: 'hidden w-40 md:table-cell',
      },
    },
    created: {
      id: 'created',
      accessorFn: (t) => time(t.created_at),
      sortDescFirst: true,
      header: ({ column }) => (
        <DataTableColumnHeader column={column} title="Created" />
      ),
      cell: ({ row }) => relativeTime(row.original.created_at),
      meta: {
        headClassName: 'hidden w-32 lg:table-cell',
        cellClassName: 'hidden w-32 text-muted-foreground lg:table-cell',
      },
    },
    last_used: {
      id: 'last_used',
      accessorFn: (t) => time(t.last_used_at),
      sortDescFirst: true,
      header: ({ column }) => (
        <DataTableColumnHeader column={column} title="Last used" />
      ),
      cell: ({ row }) => relativeTime(row.original.last_used_at),
      meta: {
        headClassName: 'hidden w-32 md:table-cell',
        cellClassName: 'hidden w-32 text-muted-foreground md:table-cell',
      },
    },
    status: {
      id: 'status',
      accessorFn: (t) => (t.revoked_at ? 'Revoked' : 'Active'),
      enableSorting: false,
      header: 'Status',
      cell: ({ row }) => (
        <TokenStatus
          token={row.original}
          data-testid={`${testIdPrefix}-status-${row.original.id}`}
        />
      ),
      meta: {
        headClassName: 'hidden w-24 sm:table-cell',
        cellClassName: 'hidden w-24 sm:table-cell',
      },
    },
    actions: onRevoke
      ? {
          id: 'actions',
          enableSorting: false,
          header: () => <span className="sr-only">Actions</span>,
          cell: ({ row }) => {
            const t = row.original;
            if (t.revoked_at || !canRevoke(t)) return null;
            return (
              <SecondaryButton
                size="sm"
                color="red"
                className="min-h-11 sm:min-h-8"
                data-testid={`${testIdPrefix}-revoke-${t.id}`}
                disabled={revoking}
                onClick={(e) => {
                  e.stopPropagation();
                  onRevoke(t);
                }}
              >
                Revoke
              </SecondaryButton>
            );
          },
          meta: {
            headClassName: 'w-24',
            cellClassName: 'w-24 text-right',
          },
        }
      : null,
  };
  return columns
    .map((id) => all[id])
    .filter((c): c is AppColumnDef<ApiToken> => c !== null);
}
