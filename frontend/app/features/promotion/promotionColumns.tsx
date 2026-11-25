import { Copy, MessageSquare, NotebookPen, Undo2 } from 'lucide-react';
import { Badge } from '~/components/ui/badge';
import { SecondaryButton } from '~/components/ui/buttons';
import {
  DataTableColumnHeader,
  DataTableRowActions,
  type AppColumnDef,
  type DataTableRowAction,
} from '~/components/ui/data-table';
import { DisplayName } from '~/components/user/avatar';
import { UserAvatar } from '~/components/user/UserAvatar';
import { ContactRecordedStatus } from './ContactRecordedStatus';
import type { DiscordPreviewOptions } from './discordPreview';
import { relativeFromIso } from './feedback';
import { isLinked, type CandidateRow, type CandidateSource } from './schemas';

export type PromotionColumnId =
  | 'player'
  | 'mmr'
  | 'activity'
  | 'status'
  | 'actions';

export const DEFAULT_PROMOTION_COLUMNS: readonly PromotionColumnId[] = [
  'player',
  'mmr',
  'activity',
  'status',
  'actions',
];

export type ComposeMode = 'message' | 'record';

/** Stable id for a row: the account pk, or the Discord id of a member without one. */
export function candidateRowId(row: CandidateRow): string {
  return row.user_pk != null
    ? String(row.user_pk)
    : `discord-${row.discordId ?? ''}`;
}

export function mmrLabel(mmr: number | null): string {
  return mmr != null ? mmr.toLocaleString('en-US') : 'Unknown';
}

export interface PromotionActionContext {
  testIdPrefix: string;
  onCompose: (row: CandidateRow, mode: ComposeMode) => void;
  onUndo: (sendId: number) => void;
  /** Row whose account is being prepared; its actions are disabled. */
  pendingRowId: string | null;
  undoPending: boolean;
  /** A send shown in the open composer with its own undo; hidden here to avoid duplicates. */
  hideUndoFor: number | null;
}

export function promotionRowActions(
  row: CandidateRow,
  ctx: PromotionActionContext,
): DataTableRowAction[] {
  const id = candidateRowId(row);
  const preparing = ctx.pendingRowId === id;
  // A contact recorded in SFG blocks another send to this player.
  const external = row.external_contact != null;
  const blockedHint = external
    ? 'Contact recorded in SFG, so messaging is off for this player.'
    : undefined;
  const actions: DataTableRowAction[] = [
    {
      key: 'message',
      label: preparing ? 'Preparing...' : 'Message',
      icon: <MessageSquare className="mr-1 size-4" aria-hidden />,
      onSelect: () => ctx.onCompose(row, 'message'),
      disabled: preparing || external,
      hint: blockedHint,
      testId: `${ctx.testIdPrefix}-message-${id}`,
    },
    {
      key: 'record',
      label: 'Mark as sent',
      icon: <NotebookPen className="mr-1 size-4" aria-hidden />,
      onSelect: () => ctx.onCompose(row, 'record'),
      disabled: preparing || external,
      hint: blockedHint,
      testId: `${ctx.testIdPrefix}-record-${id}`,
    },
  ];
  const last = row.last_messaged;
  if (last?.can_undo && last.send_id !== ctx.hideUndoFor) {
    actions.push({
      key: 'undo',
      label: 'Undo send',
      icon: <Undo2 className="mr-1 size-4" aria-hidden />,
      onSelect: () => ctx.onUndo(last.send_id),
      destructive: true,
      disabled: ctx.undoPending,
      testId: `${ctx.testIdPrefix}-undo-${id}`,
    });
  }
  return actions;
}

export interface MakePromotionColumnsOptions extends PromotionActionContext {
  source: CandidateSource;
  /** Recent tournaments counted for the "recent" source. */
  poolN: number;
  previewOptions: DiscordPreviewOptions;
  onCopyHandle: (handle: string) => void;
  columns?: readonly PromotionColumnId[];
}

function activityText(
  row: CandidateRow,
  source: CandidateSource,
  poolN: number,
  opts: DiscordPreviewOptions,
): string | null {
  if (source === 'recent' && row.recent_count != null)
    return `Played ${row.recent_count} of the last ${poolN}`;
  if (source === 'active' && row.last_active_at)
    return `Active ${relativeFromIso(row.last_active_at, opts)}`;
  if (source === 'discord' && row.discord_joined_at)
    return `Joined Discord ${relativeFromIso(row.discord_joined_at, opts)}`;
  return null;
}

function activitySortValue(
  row: CandidateRow,
  source: CandidateSource,
): number | undefined {
  if (source === 'recent') return row.recent_count ?? undefined;
  const iso = source === 'active' ? row.last_active_at : row.discord_joined_at;
  const ms = iso ? new Date(iso).getTime() : NaN;
  return Number.isNaN(ms) ? undefined : ms;
}

const ACTIVITY_TITLE: Record<CandidateSource, string> = {
  recent: 'Recent play',
  active: 'Last active',
  discord: 'Joined Discord',
};

function StatusBadges({
  row,
  testIdPrefix,
}: {
  row: CandidateRow;
  testIdPrefix: string;
}) {
  if (!row.signed_up && isLinked(row)) return null;
  return (
    <span
      className="flex flex-wrap gap-1"
      data-testid={`${testIdPrefix}-badges-${candidateRowId(row)}`}
    >
      {row.signed_up && <Badge variant="secondary">Signed up</Badge>}
      {!isLinked(row) && <Badge variant="outline">No account yet</Badge>}
    </span>
  );
}

function messagedText(row: CandidateRow, opts: DiscordPreviewOptions): string {
  const last = row.last_messaged!;
  return `Messaged by ${last.by ?? 'someone'}, ${relativeFromIso(last.sent_at, opts)}`;
}

/**
 * Column defs for PromotionTable. Phones show the player with MMR, activity
 * and status stacked under the name plus the actions menu; MMR appears from
 * `sm`, activity from `md`, status from `lg`; inline actions from `md`.
 */
export function makePromotionColumns({
  source,
  poolN,
  previewOptions,
  onCopyHandle,
  columns = DEFAULT_PROMOTION_COLUMNS,
  ...ctx
}: MakePromotionColumnsOptions): AppColumnDef<CandidateRow>[] {
  const { testIdPrefix } = ctx;
  const all: Record<PromotionColumnId, AppColumnDef<CandidateRow>> = {
    player: {
      id: 'player',
      accessorFn: (r) => DisplayName(r),
      sortFn: 'alphanumeric',
      header: ({ column }) => (
        <DataTableColumnHeader column={column} title="Player" />
      ),
      cell: ({ row }) => {
        const r = row.original;
        const id = candidateRowId(r);
        const activity = activityText(r, source, poolN, previewOptions);
        return (
          <div className="flex min-w-0 items-start gap-2">
            <UserAvatar user={{ ...r, pk: r.user_pk ?? undefined }} size="sm" />
            <div className="flex min-w-0 flex-col gap-0.5">
              <span className="font-medium wrap-anywhere">
                {DisplayName(r)}
              </span>
              {r.discordUsername && (
                <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
                  <span className="wrap-anywhere">
                    {/* eslint-disable-next-line draftforge/use-display-name -- the Discord @handle shown next to its copy button */}
                    @{r.discordUsername}
                  </span>
                  <SecondaryButton
                    type="button"
                    size="icon"
                    className="size-6 shrink-0"
                    onClick={(e) => {
                      e.stopPropagation();
                      onCopyHandle(r.discordUsername!);
                    }}
                    aria-label={`Copy Discord username of ${DisplayName(r)}`}
                    data-testid={`promo-copy-discord-${id}`}
                  >
                    <Copy className="size-3" />
                  </SecondaryButton>
                </span>
              )}
              <span
                className="text-xs text-muted-foreground tabular-nums sm:hidden"
                data-testid={`${testIdPrefix}-mmr-stacked-${id}`}
              >
                {`MMR ${mmrLabel(r.mmr)}`}
              </span>
              {activity && (
                <span className="text-xs text-muted-foreground md:hidden">
                  {activity}
                </span>
              )}
              <span className="flex flex-col gap-0.5 lg:hidden">
                <StatusBadges
                  row={r}
                  testIdPrefix={`${testIdPrefix}-stacked`}
                />
                {r.last_messaged && (
                  <span className="text-xs text-muted-foreground">
                    {messagedText(r, previewOptions)}
                  </span>
                )}
                {r.external_contact && (
                  <span className="text-xs text-muted-foreground">
                    Contact recorded in SFG
                  </span>
                )}
              </span>
            </div>
          </div>
        );
      },
    },
    mmr: {
      id: 'mmr',
      accessorFn: (r) => r.mmr ?? undefined,
      sortUndefined: 'last',
      sortDescFirst: true,
      header: ({ column }) => (
        <DataTableColumnHeader column={column} title="MMR" />
      ),
      cell: ({ row }) => {
        const { mmr } = row.original;
        return (
          <span
            className={mmr == null ? 'text-muted-foreground' : undefined}
            data-testid={`${testIdPrefix}-mmr-${candidateRowId(row.original)}`}
          >
            {mmrLabel(mmr)}
          </span>
        );
      },
      meta: {
        headClassName: 'hidden w-24 text-right sm:table-cell',
        cellClassName: 'hidden w-24 text-right tabular-nums sm:table-cell',
      },
    },
    activity: {
      id: 'activity',
      accessorFn: (r) => activitySortValue(r, source),
      sortUndefined: 'last',
      sortDescFirst: true,
      header: ({ column }) => (
        <DataTableColumnHeader column={column} title={ACTIVITY_TITLE[source]} />
      ),
      cell: ({ row }) => (
        <span className="text-sm text-muted-foreground">
          {activityText(row.original, source, poolN, previewOptions) ?? '—'}
        </span>
      ),
      meta: {
        headClassName: 'hidden w-40 md:table-cell',
        cellClassName: 'hidden w-40 md:table-cell',
      },
    },
    status: {
      id: 'status',
      enableSorting: false,
      header: 'Status',
      cell: ({ row }) => {
        const r = row.original;
        return (
          <div className="flex flex-col gap-1">
            <StatusBadges row={r} testIdPrefix={testIdPrefix} />
            {(r.last_messaged || r.external_contact) && (
              <span className="flex flex-col gap-1 text-xs text-muted-foreground">
                <ContactRecordedStatus
                  externalContact={r.external_contact}
                  localLastMessaged={r.last_messaged}
                  testId={candidateRowId(r)}
                />
              </span>
            )}
            {!r.signed_up &&
              isLinked(r) &&
              !r.last_messaged &&
              !r.external_contact && (
                <span className="text-xs text-muted-foreground">
                  Not messaged
                </span>
              )}
          </div>
        );
      },
      meta: {
        headClassName: 'hidden w-56 lg:table-cell',
        cellClassName: 'hidden w-56 lg:table-cell',
      },
    },
    actions: {
      id: 'actions',
      enableSorting: false,
      header: () => <span className="sr-only">Actions</span>,
      cell: ({ row }) => (
        <DataTableRowActions
          label={`Actions for ${DisplayName(row.original)}`}
          actions={promotionRowActions(row.original, ctx)}
          inlineFrom="md"
          data-testid={`${testIdPrefix}-actions-${candidateRowId(row.original)}`}
        />
      ),
      meta: {
        headClassName: 'w-16 sm:w-14 md:w-80',
        cellClassName: 'w-16 text-right sm:w-14 md:w-80',
      },
    },
  };
  return columns.map((id) => all[id]);
}
