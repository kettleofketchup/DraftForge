import { ArrowRight } from 'lucide-react';
import type { ReactNode } from 'react';

import { EventStateBadge } from '~/components/events/EventStateBadge';
import type { SignupHistoryEntry } from '~/components/events/schemas';
import {
  actionLabel,
  actionTone,
  causePhrase,
  describeDiff,
  diffPartText,
  extraNotes,
  formatHistoryTime,
  meansLabel,
  type DiffPart,
} from '~/components/events/signupHistory';
import { Badge } from '~/components/ui/badge';
import type { AppColumnDef } from '~/components/ui/data-table';
import { LazyTooltip } from '~/components/ui/tooltip';
import { UserAvatar } from '~/components/user/UserAvatar';
import { DisplayName } from '~/components/user/avatar';
import { cn } from '~/lib/utils';

export type SignupHistoryColumnId = 'when' | 'change' | 'actor' | 'means';

export const DEFAULT_SIGNUP_HISTORY_COLUMNS: readonly SignupHistoryColumnId[] =
  ['when', 'change', 'actor', 'means'];

export interface MakeSignupHistoryColumnsOptions {
  columns?: readonly SignupHistoryColumnId[];
  eventTimezone?: string;
  /** Sheet layout: the meta line shows at every width. */
  compact?: boolean;
  loadedById: Map<number, SignupHistoryEntry>;
  originalId: number | null;
}

export function HistoryTime({
  iso,
  eventTimezone,
}: {
  iso: string;
  eventTimezone?: string;
}) {
  const { short, full } = formatHistoryTime(iso, eventTimezone);
  return (
    <LazyTooltip content={full}>
      <time dateTime={iso}>{short}</time>
    </LazyTooltip>
  );
}

function ActorName({ entry }: { entry: SignupHistoryEntry }) {
  const { actor } = entry;
  if (actor.role === 'system' || actor.user_id == null) return <>System</>;
  return (
    <span className="inline-flex min-w-0 items-center gap-1.5">
      <UserAvatar user={actor} size="xs" />
      <span className="wrap-anywhere">{DisplayName(actor)}</span>
    </span>
  );
}

function MeansBadge({
  entry,
  testId,
}: {
  entry: SignupHistoryEntry;
  testId: string;
}) {
  return (
    <Badge variant="outline" data-testid={testId}>
      {meansLabel(entry)}
    </Badge>
  );
}

function StatusPart({ part }: { part: DiffPart }) {
  const to = <EventStateBadge state={String(part.to ?? '')} />;
  if (part.from == null) return to;
  return (
    <span className="inline-flex flex-wrap items-center gap-1">
      <EventStateBadge state={String(part.from)} />
      <ArrowRight className="size-3 text-muted-foreground" aria-hidden />
      <span className="sr-only">changed to</span>
      {to}
    </span>
  );
}

function DiffLine({
  entry,
  eventTimezone,
}: {
  entry: SignupHistoryEntry;
  eventTimezone?: string;
}) {
  const diff = describeDiff(entry);
  let body: ReactNode;
  if ('unavailable' in diff) {
    body = 'Details unavailable';
  } else if ('note' in diff) {
    body = diff.note;
  } else {
    body = diff.map((part) =>
      part.field === 'status' ? (
        <StatusPart key={part.field} part={part} />
      ) : (
        <span key={part.field}>
          {diffPartText(part, entry.action, eventTimezone)}
        </span>
      ),
    );
  }
  return (
    <div
      data-testid="signup-history-diff"
      className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm"
    >
      {body}
    </div>
  );
}

function ChangeCell({
  entry,
  eventTimezone,
  compact,
  loadedById,
  isOriginal,
}: {
  entry: SignupHistoryEntry;
  eventTimezone?: string;
  compact: boolean;
  loadedById: Map<number, SignupHistoryEntry>;
  isOriginal: boolean;
}) {
  const cause = causePhrase(entry, loadedById);
  const notes = extraNotes(entry);
  const rules = entry.rules_overridden;
  return (
    <div className="flex min-w-0 flex-col gap-1.5">
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        <UserAvatar user={entry.subject} size="xs" />
        <span className="wrap-anywhere font-medium">
          {DisplayName(entry.subject)}
        </span>
        <Badge variant="outline" className={actionTone(entry.action)}>
          {actionLabel(entry.action)}
        </Badge>
        {isOriginal && (
          <Badge
            variant="outline"
            className="border-primary/30 bg-primary/20 text-primary"
            data-testid="signup-history-original"
          >
            Original sign-up
          </Badge>
        )}
        {rules.length > 0 && (
          <LazyTooltip content={rules.join(', ')}>
            <Badge
              variant="outline"
              className="border-warning/30 bg-warning/20 text-warning"
              tabIndex={0}
              data-testid="signup-history-rules-chip"
            >
              {`Overrode ${rules.length} ${rules.length === 1 ? 'rule' : 'rules'}`}
            </Badge>
          </LazyTooltip>
        )}
      </div>
      <DiffLine entry={entry} eventTimezone={eventTimezone} />
      {cause && (
        <span
          className="text-xs text-muted-foreground"
          data-testid="signup-history-cause"
        >
          {cause}
        </span>
      )}
      {entry.reason && (
        <p
          className="wrap-anywhere rounded-md border border-border bg-base-200 px-2 py-1 text-sm"
          data-testid="signup-history-reason"
        >
          <span className="text-muted-foreground">Reason: </span>
          {entry.reason}
        </p>
      )}
      {notes.length > 0 && (
        <ul className="flex flex-col gap-0.5 text-xs text-muted-foreground">
          {notes.map((note) => (
            <li key={note} data-testid="signup-history-note">
              {note}
            </li>
          ))}
        </ul>
      )}
      <div
        data-testid="signup-history-meta"
        className={cn(
          'flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground',
          !compact && 'md:hidden',
        )}
      >
        <HistoryTime iso={entry.occurred_at} eventTimezone={eventTimezone} />
        <span aria-hidden>·</span>
        <ActorName entry={entry} />
        {entry.on_behalf && <span>on behalf</span>}
        <MeansBadge entry={entry} testId="signup-history-meta-means" />
      </div>
    </div>
  );
}

/**
 * Column defs for SignupHistoryTable. Phones show only the change cell, with
 * time, actor and means stacked in its meta line; the others appear from `sm`/`md`.
 */
export function makeSignupHistoryColumns({
  columns = DEFAULT_SIGNUP_HISTORY_COLUMNS,
  eventTimezone,
  compact = false,
  loadedById,
  originalId,
}: MakeSignupHistoryColumnsOptions): AppColumnDef<SignupHistoryEntry>[] {
  const all: Record<SignupHistoryColumnId, AppColumnDef<SignupHistoryEntry>> = {
    when: {
      id: 'when',
      accessorKey: 'occurred_at',
      enableSorting: false,
      header: 'When',
      cell: ({ row }) => (
        <HistoryTime
          iso={row.original.occurred_at}
          eventTimezone={eventTimezone}
        />
      ),
      meta: {
        headClassName: 'hidden w-36 sm:table-cell',
        cellClassName: 'hidden w-36 text-muted-foreground sm:table-cell',
      },
    },
    change: {
      id: 'change',
      accessorKey: 'action',
      enableSorting: false,
      header: 'Change',
      cell: ({ row }) => (
        <ChangeCell
          entry={row.original}
          eventTimezone={eventTimezone}
          compact={compact}
          loadedById={loadedById}
          isOriginal={row.original.id === originalId}
        />
      ),
    },
    actor: {
      id: 'actor',
      accessorFn: (e) => e.actor.user_id,
      enableSorting: false,
      header: 'Actor',
      cell: ({ row }) => (
        <div
          className="flex min-w-0 flex-col gap-0.5"
          data-testid="signup-history-actor"
        >
          <ActorName entry={row.original} />
          {row.original.on_behalf && (
            <span className="text-xs text-muted-foreground">on behalf</span>
          )}
        </div>
      ),
      meta: {
        headClassName: 'hidden w-44 md:table-cell',
        cellClassName: 'hidden w-44 md:table-cell',
      },
    },
    means: {
      id: 'means',
      accessorKey: 'means',
      enableSorting: false,
      header: 'Means',
      cell: ({ row }) => (
        <MeansBadge entry={row.original} testId="signup-history-means" />
      ),
      meta: {
        headClassName: 'hidden w-32 sm:table-cell',
        cellClassName: 'hidden w-32 sm:table-cell',
      },
    },
  };
  return columns.map((id) => all[id]);
}
