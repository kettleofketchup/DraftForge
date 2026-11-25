import { formatDistanceToNow } from 'date-fns';
import { Copy } from 'lucide-react';

import { Badge } from '~/components/ui/badge';
import { SecondaryButton } from '~/components/ui/buttons';
import type { AppColumnDef } from '~/components/ui/data-table';
import { cn } from '~/lib/utils';

import {
  isAllowedExternalLink,
  type AccessState,
  type BotAccessRow,
  type BotStatus,
} from './schemas';

const STATUS_LABEL: Record<BotStatus, string> = {
  available: 'Available',
  busy: 'Busy',
  connecting: 'Connecting',
  offline: 'Offline',
  unknown: 'Unknown',
};

const STATUS_CLASS: Record<BotStatus, string> = {
  available: 'border-success/40 text-success',
  busy: 'border-warning/40 text-warning',
  connecting: 'border-info/40 text-info',
  offline: 'text-muted-foreground',
  unknown: 'text-muted-foreground',
};

const ACCESS_LABEL: Record<AccessState, string> = {
  verified: '✓ Verified',
  unverified: 'Unverified',
  missing: '✗ Missing',
  unknown: 'Unknown',
};

const ACCESS_CLASS: Record<AccessState, string> = {
  verified: 'text-success',
  unverified: 'text-warning',
  missing: 'text-destructive',
  unknown: 'text-muted-foreground',
};

const ACCESS_NOTE: Record<NonNullable<BotAccessRow['access_note']>, string> = {
  not_rechecked: 'not re-checked since the lobby service restarted',
  allowed_unverified:
    "lobbies are still routed to it, but Valve doesn't list it as an admin",
};

const ROW_REFRESH_NOTE: Partial<
  Record<NonNullable<BotAccessRow['refresh']>, string>
> = {
  not_ready: 'bot not online, kept last result',
  failed: 'check failed, kept last result',
};

function StatusBadge({ status }: { status: BotStatus | null }) {
  if (status === null) return <span className="text-muted-foreground">—</span>;
  return (
    <Badge variant="outline" className={STATUS_CLASS[status]}>
      {STATUS_LABEL[status]}
    </Badge>
  );
}

function checkedAgo(iso: string | null): string | null {
  return iso ? formatDistanceToNow(new Date(iso), { addSuffix: true }) : null;
}

function displayUrl(url: string): string {
  return url.replace(/^https:\/\//, '');
}

function AccessCell({ row: r }: { row: BotAccessRow }) {
  const ago = checkedAgo(r.access_checked_at);
  const refreshNote = r.refresh ? ROW_REFRESH_NOTE[r.refresh] : undefined;
  return (
    <div className="flex flex-col gap-0.5 text-sm">
      <span className={cn('font-medium', ACCESS_CLASS[r.access])}>
        {ACCESS_LABEL[r.access]}
        {ago ? (
          <span className="font-normal text-muted-foreground"> · {ago}</span>
        ) : null}
      </span>
      {r.access_note ? (
        <span className="text-xs text-muted-foreground">
          {ACCESS_NOTE[r.access_note]}
        </span>
      ) : null}
      {refreshNote ? (
        <span className="text-xs text-muted-foreground">{refreshNote}</span>
      ) : null}
    </div>
  );
}

function IdentityCell({
  row: r,
  onCopy,
}: {
  row: BotAccessRow;
  onCopy: (url: string) => void;
}) {
  if (!r.identity) {
    return (
      <span className="text-sm text-muted-foreground">
        Not available until the bot logs on
      </span>
    );
  }
  const url = r.identity.profile_url;
  if (!url || !isAllowedExternalLink(url)) {
    return <span className="wrap-anywhere">{r.identity.value}</span>;
  }
  const emphasize = r.access === 'missing' || r.access === 'unknown';
  return (
    <div className="flex min-w-0 items-center gap-2">
      <a
        href={url}
        target="_blank"
        rel="noopener noreferrer"
        data-testid={`bot-access-profile-link-${r.position}`}
        className={cn(
          'min-w-0 wrap-anywhere hover:underline',
          emphasize ? 'font-medium text-foreground' : 'text-muted-foreground',
        )}
      >
        {displayUrl(url)}
      </a>
      <SecondaryButton
        type="button"
        size="sm"
        className="min-h-11 shrink-0 sm:min-h-8"
        aria-label={`Copy link for Bot ${r.position}`}
        data-testid={`bot-access-copy-${r.position}`}
        onClick={(e) => {
          e.stopPropagation();
          onCopy(url);
        }}
      >
        <Copy className="size-4" aria-hidden="true" />
        <span className="hidden sm:inline">Copy</span>
      </SecondaryButton>
    </div>
  );
}

export interface MakeBotAccessColumnsOptions {
  onCopy: (url: string) => void;
  identityLabel: string;
  /** One full-width column with every field stacked, for phones. */
  stacked?: boolean;
}

/** Column defs for the bot access table. */
export function makeBotAccessColumns({
  onCopy,
  identityLabel,
  stacked = false,
}: MakeBotAccessColumnsOptions): AppColumnDef<BotAccessRow>[] {
  if (stacked) {
    return [
      {
        id: 'bot',
        accessorFn: (r) => r.position,
        enableSorting: false,
        header: 'Bot',
        cell: ({ row }) => (
          <div className="flex min-w-0 flex-col gap-2">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium">Bot {row.original.position}</span>
              <StatusBadge status={row.original.status} />
            </div>
            <AccessCell row={row.original} />
            <div className="flex min-w-0 flex-col gap-1">
              <span className="text-xs text-muted-foreground">
                {identityLabel}
              </span>
              <IdentityCell row={row.original} onCopy={onCopy} />
            </div>
          </div>
        ),
      },
    ];
  }
  return [
    {
      id: 'bot',
      accessorFn: (r) => r.position,
      enableSorting: false,
      header: 'Bot',
      cell: ({ row }) => (
        <span className="font-medium">Bot {row.original.position}</span>
      ),
      meta: { headClassName: 'w-24', cellClassName: 'w-24' },
    },
    {
      id: 'status',
      accessorFn: (r) => r.status ?? '',
      enableSorting: false,
      header: 'Status',
      cell: ({ row }) => <StatusBadge status={row.original.status} />,
      meta: { headClassName: 'w-32', cellClassName: 'w-32' },
    },
    {
      id: 'access',
      accessorFn: (r) => r.access,
      enableSorting: false,
      header: 'League access',
      cell: ({ row }) => <AccessCell row={row.original} />,
      meta: { headClassName: 'w-52', cellClassName: 'w-52' },
    },
    {
      id: 'identity',
      accessorFn: (r) => r.identity?.value ?? '',
      enableSorting: false,
      header: identityLabel,
      cell: ({ row }) => <IdentityCell row={row.original} onCopy={onCopy} />,
    },
  ];
}
