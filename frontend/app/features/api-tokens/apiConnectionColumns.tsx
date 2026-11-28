import { Badge } from '~/components/ui/badge';
import { SecondaryButton } from '~/components/ui/buttons';
import {
  DataTableColumnHeader,
  type AppColumnDef,
} from '~/components/ui/data-table';
import { UserAvatar } from '~/components/user/UserAvatar';
import { DisplayName } from '~/components/user/avatar';
import { maskedToken, relativeTime } from './apiTokenColumns';
import type { ApiConnection } from './connectionSchemas';
import type { ApiUserRef } from './schemas';

export type ApiConnectionColumnId =
  | 'name'
  | 'directions'
  | 'status'
  | 'key'
  | 'last_sync'
  | 'actions';

export const DEFAULT_API_CONNECTION_COLUMNS: readonly ApiConnectionColumnId[] =
  ['name', 'directions', 'status', 'key', 'last_sync', 'actions'];

type BadgeVariant = 'default' | 'secondary' | 'destructive' | 'outline';

export function connectionStatus(row: ApiConnection): {
  label: string;
  variant: BadgeVariant;
} {
  if (row.archived_at) return { label: 'Archived', variant: 'outline' };
  if (!row.enabled) return { label: 'Disabled', variant: 'outline' };
  if (row.last_error_code) return { label: 'Error', variant: 'destructive' };
  return { label: 'Enabled', variant: 'secondary' };
}

/** Enabled directions, by name; switched-off ones are not listed. */
export function connectionDirections(row: ApiConnection): string[] {
  const directions: string[] = [];
  if (row.inbound_enabled) directions.push('Inbound');
  if (row.mmr_push_enabled) directions.push('MMR push');
  if (row.mmr_pull_enabled) directions.push('MMR pull');
  if (row.promotion_push_enabled) directions.push('Promotion push');
  return directions;
}

export function activeCredentials(row: ApiConnection) {
  return row.inbound_credentials.filter((c) => c.revoked_at === null);
}

export type KeyOwners = ReadonlyMap<number, ApiUserRef | null>;

/** The owner of the connection's first active key, when known. */
export function keyOwner(
  row: ApiConnection,
  owners: KeyOwners | undefined,
): ApiUserRef | null {
  for (const key of activeCredentials(row)) {
    const owner = owners?.get(key.id);
    if (owner) return owner;
  }
  return null;
}

export function lastSyncText(row: ApiConnection): string {
  return relativeTime(row.last_success_at);
}

export interface MakeApiConnectionColumnsOptions {
  testIdPrefix: string;
  columns?: readonly ApiConnectionColumnId[];
  onManage?: (row: ApiConnection) => void;
  /** Legacy token id to owner, from the token list. */
  keyOwners?: KeyOwners;
}

export function makeApiConnectionColumns({
  testIdPrefix,
  columns = DEFAULT_API_CONNECTION_COLUMNS,
  onManage,
  keyOwners,
}: MakeApiConnectionColumnsOptions): AppColumnDef<ApiConnection>[] {
  const all: Record<ApiConnectionColumnId, AppColumnDef<ApiConnection> | null> =
    {
      name: {
        id: 'name',
        accessorKey: 'name',
        header: ({ column }) => (
          <DataTableColumnHeader column={column} title="Name" />
        ),
        cell: ({ row }) => {
          const c = row.original;
          const directions = connectionDirections(c);
          const owner = keyOwner(c, keyOwners);
          return (
            <div className="flex min-w-0 flex-col gap-0.5">
              <span className="wrap-anywhere font-medium">{c.name}</span>
              <span
                className="text-xs text-muted-foreground md:hidden"
                data-testid={`${testIdPrefix}-summary-${c.id}`}
              >
                {connectionStatus(c).label} ·{' '}
                {directions.length ? directions.join(', ') : 'No directions'} ·{' '}
                {lastSyncText(c)}
                {owner ? ` · key by ${DisplayName(owner)}` : ''}
              </span>
            </div>
          );
        },
      },
      directions: {
        id: 'directions',
        header: 'Directions',
        enableSorting: false,
        accessorFn: (c) => connectionDirections(c).join(', '),
        cell: ({ row }) => {
          const directions = connectionDirections(row.original);
          return (
            <span
              className={
                directions.length ? undefined : 'text-muted-foreground'
              }
              data-testid={`${testIdPrefix}-directions-${row.original.id}`}
            >
              {directions.length ? directions.join(', ') : 'None'}
            </span>
          );
        },
        meta: {
          headClassName: 'hidden w-40 md:table-cell',
          cellClassName: 'hidden w-40 md:table-cell',
        },
      },
      status: {
        id: 'status',
        header: 'Status',
        enableSorting: false,
        accessorFn: (c) => connectionStatus(c).label,
        cell: ({ row }) => {
          const status = connectionStatus(row.original);
          return (
            <Badge
              variant={status.variant}
              data-testid={`${testIdPrefix}-status-${row.original.id}`}
            >
              {status.label}
            </Badge>
          );
        },
        meta: {
          headClassName: 'hidden w-24 md:table-cell',
          cellClassName: 'hidden w-24 md:table-cell',
        },
      },
      key: {
        id: 'key',
        header: 'Inbound key',
        enableSorting: false,
        accessorFn: (c) => activeCredentials(c)[0]?.prefix ?? '',
        cell: ({ row }) => {
          const keys = activeCredentials(row.original);
          const owner = keyOwner(row.original, keyOwners);
          return keys.length ? (
            <div className="flex min-w-0 flex-col gap-1">
              <code className="font-mono text-xs wrap-anywhere">
                {keys.map((k) => maskedToken(k.prefix)).join(', ')}
              </code>
              {owner && (
                <span
                  className="flex min-w-0 items-center gap-2 text-xs"
                  data-testid={`${testIdPrefix}-key-owner-${row.original.id}`}
                >
                  <UserAvatar user={owner} size="xs" />
                  <span className="truncate">{DisplayName(owner)}</span>
                </span>
              )}
            </div>
          ) : (
            <span className="text-muted-foreground">None</span>
          );
        },
        meta: {
          headClassName: 'hidden w-40 lg:table-cell',
          cellClassName: 'hidden w-40 lg:table-cell',
        },
      },
      last_sync: {
        id: 'last_sync',
        accessorFn: (c) =>
          c.last_success_at ? new Date(c.last_success_at).getTime() : 0,
        header: ({ column }) => (
          <DataTableColumnHeader column={column} title="Last sync" />
        ),
        cell: ({ row }) => (
          <span className="text-muted-foreground">
            {lastSyncText(row.original)}
          </span>
        ),
        meta: {
          headClassName: 'hidden w-28 md:table-cell',
          cellClassName: 'hidden w-28 md:table-cell',
        },
      },
      actions: onManage
        ? {
            id: 'actions',
            header: () => <span className="sr-only">Actions</span>,
            enableSorting: false,
            cell: ({ row }) => (
              <SecondaryButton
                type="button"
                size="sm"
                className="min-h-11 sm:min-h-8"
                onClick={(e) => {
                  e.stopPropagation();
                  onManage(row.original);
                }}
                aria-label={`Manage ${row.original.name}`}
                data-testid={`${testIdPrefix}-manage-${row.original.id}`}
              >
                Manage
              </SecondaryButton>
            ),
            meta: { headClassName: 'w-24', cellClassName: 'w-24' },
          }
        : null,
    };
  return columns.flatMap((id) => {
    const col = all[id];
    return col ? [col] : [];
  });
}
