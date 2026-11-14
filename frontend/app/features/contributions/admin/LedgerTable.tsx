import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router';
import { toast } from 'sonner';
import {
  BrandSelect,
  BrandSelectContent,
  BrandSelectItem,
  BrandSelectTrigger,
  SelectValue,
} from '~/components/ui/brand-select';
import { EditIconButton, SecondaryButton, TrashIconButton } from '~/components/ui/buttons';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '~/components/ui/dialog';
import { ConfirmDialog } from '~/components/ui/dialogs';
import { UserAvatar } from '~/components/user/UserAvatar';
import type { OrgFeatureAccess } from '~/features/org-features';
import { extractApiError } from '~/lib/apiError';
import { getLogger } from '~/lib/logger';
import { useDeleteManualAward, useLedgerEntries } from '../queries';
import {
  ALL_TIME,
  CONTRIBUTION_KINDS,
  ENTRIES_PAGE_SIZE,
  KIND_LABELS,
  type AdminEntry,
  type ContributionKind,
  type EntriesFilters,
} from '../schemas';
import { formatOrgDate, periodOptions } from '../timezone';
import { ManualAwardForm, type AwardEvent, type AwardMember } from './ManualAwardForm';

const log = getLogger('LedgerTable');

const ALL_KINDS = 'all';

export interface LedgerTableProps {
  orgId: number;
  access: OrgFeatureAccess;
  timeZone: string | undefined;
  members: AwardMember[];
  events: AwardEvent[];
}

export function LedgerTable({ orgId, access, timeZone, members, events }: LedgerTableProps) {
  const [filters, setFilters] = useState<EntriesFilters>({
    period: ALL_TIME,
    kind: null,
    offset: 0,
  });
  const [editing, setEditing] = useState<AdminEntry | null>(null);
  const [deleting, setDeleting] = useState<AdminEntry | null>(null);
  const options = useMemo(() => periodOptions(timeZone), [timeZone]);
  const { data, isLoading, isError, error, isFetching } = useLedgerEntries(
    orgId,
    access,
    filters,
  );
  const remove = useDeleteManualAward(orgId, access);

  useEffect(() => {
    if (!data || data.offset === 0 || data.offset < data.count) return;
    const lastPageOffset = Math.max(
      0,
      (Math.ceil(data.count / ENTRIES_PAGE_SIZE) - 1) * ENTRIES_PAGE_SIZE,
    );
    setFilters((f) => (f.offset === data.offset ? { ...f, offset: lastPageOffset } : f));
  }, [data]);

  const confirmDelete = async (): Promise<void> => {
    if (!deleting) return;
    try {
      await remove.mutateAsync(deleting.pk);
      toast.success('Award deleted');
    } catch (err) {
      log.warn('Failed to delete manual award', { orgId, entryPk: deleting.pk, err });
      toast.error(extractApiError(err) ?? 'Failed to delete award');
    }
  };

  const page = data ? Math.floor(data.offset / ENTRIES_PAGE_SIZE) + 1 : 1;
  const pages = data ? Math.max(1, Math.ceil(data.count / ENTRIES_PAGE_SIZE)) : 1;

  return (
    <section className="flex flex-col gap-3" data-testid="contributions-ledger">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h4 className="font-semibold">Ledger</h4>
        <div className="flex flex-wrap gap-2">
          <BrandSelect
            value={filters.period}
            onValueChange={(period) => setFilters((f) => ({ ...f, period, offset: 0 }))}
          >
            <BrandSelectTrigger
              className="min-w-40"
              aria-label="Ledger period"
              data-testid="ledger-period-select"
            >
              <SelectValue />
            </BrandSelectTrigger>
            <BrandSelectContent>
              {options.map((option) => (
                <BrandSelectItem key={option.value} value={option.value}>
                  {option.label}
                </BrandSelectItem>
              ))}
            </BrandSelectContent>
          </BrandSelect>
          <BrandSelect
            value={filters.kind ?? ALL_KINDS}
            onValueChange={(kind) =>
              setFilters((f) => ({
                ...f,
                kind: kind === ALL_KINDS ? null : (kind as ContributionKind),
                offset: 0,
              }))
            }
          >
            <BrandSelectTrigger
              className="min-w-40"
              aria-label="Ledger kind"
              data-testid="ledger-kind-select"
            >
              <SelectValue />
            </BrandSelectTrigger>
            <BrandSelectContent>
              <BrandSelectItem value={ALL_KINDS}>All kinds</BrandSelectItem>
              {CONTRIBUTION_KINDS.map((kind) => (
                <BrandSelectItem key={kind} value={kind}>
                  {KIND_LABELS[kind]}
                </BrandSelectItem>
              ))}
            </BrandSelectContent>
          </BrandSelect>
        </div>
      </div>

      {isLoading && <p className="text-sm text-muted-foreground">Loading ledger...</p>}
      {isError && (
        <p className="text-sm text-destructive" data-testid="ledger-error">
          {extractApiError(error) ?? 'Could not load the ledger.'}
        </p>
      )}

      {data && data.results.length === 0 && (
        <p className="text-sm text-muted-foreground">No entries match these filters</p>
      )}

      {data && data.results.length > 0 && (
        <ul className="flex flex-col divide-y divide-border">
          {data.results.map((entry) => (
            <li
              key={entry.pk}
              className="flex items-start justify-between gap-3 py-2"
              data-testid={`ledger-row-${entry.pk}`}
            >
              <div className="min-w-0">
                <div className="flex items-center gap-2 font-medium">
                  <UserAvatar
                    user={{
                      pk: entry.member.user_pk,
                      username: entry.member.username,
                      nickname: entry.member.nickname,
                      avatarUrl: entry.member.avatarUrl,
                    }}
                    size="sm"
                  />
                  <span className="min-w-0 truncate">
                    {entry.member.nickname || entry.member.username}
                    <span className="text-muted-foreground"> · {KIND_LABELS[entry.kind]}</span>
                  </span>
                </div>
                <div className="truncate text-sm text-muted-foreground">
                  {formatOrgDate(entry.occurred_at, timeZone)}
                  {entry.event ? (
                    <>
                      {' · '}
                      <Link to={`/events/${entry.event.id}`} className="hover:underline">
                        {entry.event.name}
                      </Link>
                    </>
                  ) : entry.event_name ? (
                    ` · ${entry.event_name}`
                  ) : null}
                  {entry.awarded_by && ` · by ${entry.awarded_by.username}`}
                </div>
                {entry.reason && (
                  <div className="text-sm text-muted-foreground">{entry.reason}</div>
                )}
              </div>
              <div className="flex shrink-0 items-center gap-1">
                <span className="mr-1 font-semibold tabular-nums">+{entry.points}</span>
                {entry.kind === 'manual' && (
                  <>
                    <EditIconButton
                      tooltip="Edit award"
                      aria-label="Edit award"
                      onClick={() => setEditing(entry)}
                      data-testid={`ledger-edit-${entry.pk}`}
                    />
                    <TrashIconButton
                      size="sm"
                      tooltip="Delete award"
                      aria-label="Delete award"
                      onClick={() => setDeleting(entry)}
                      data-testid={`ledger-delete-${entry.pk}`}
                    />
                  </>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}

      {data && data.count > ENTRIES_PAGE_SIZE && (
        <div className="flex items-center justify-between gap-2 text-sm">
          <SecondaryButton
            type="button"
            size="sm"
            disabled={filters.offset === 0 || isFetching}
            onClick={() =>
              setFilters((f) => ({ ...f, offset: Math.max(0, f.offset - ENTRIES_PAGE_SIZE) }))
            }
            data-testid="ledger-prev"
          >
            Previous
          </SecondaryButton>
          <span className="text-muted-foreground" data-testid="ledger-page">
            Page {page} of {pages}
          </span>
          <SecondaryButton
            type="button"
            size="sm"
            disabled={filters.offset + ENTRIES_PAGE_SIZE >= data.count || isFetching}
            onClick={() => setFilters((f) => ({ ...f, offset: f.offset + ENTRIES_PAGE_SIZE }))}
            data-testid="ledger-next"
          >
            Next
          </SecondaryButton>
        </div>
      )}

      <Dialog open={editing != null} onOpenChange={(open) => !open && setEditing(null)}>
        <DialogContent className="max-w-[calc(100%-2rem)] sm:max-w-lg" data-testid="ledger-edit-dialog">
          <DialogHeader>
            <DialogTitle>Edit manual award</DialogTitle>
            <DialogDescription>Changes update this member's total right away.</DialogDescription>
          </DialogHeader>
          {editing && (
            <ManualAwardForm
              key={editing.pk}
              orgId={orgId}
              access={access}
              timeZone={timeZone}
              members={members}
              events={events}
              entry={editing}
              onDone={() => setEditing(null)}
            />
          )}
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={deleting != null}
        onOpenChange={(open) => !open && setDeleting(null)}
        title="Delete this award?"
        description={
          deleting
            ? `${deleting.points} points for ${deleting.member.nickname || deleting.member.username} will be removed.`
            : ''
        }
        confirmLabel="Delete"
        variant="destructive"
        isLoading={remove.isPending}
        onConfirm={confirmDelete}
        confirmTestId="ledger-delete-confirm"
        cancelTestId="ledger-delete-cancel"
      />
    </section>
  );
}
