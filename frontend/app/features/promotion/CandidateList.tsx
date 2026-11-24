import { Copy, Info, Undo2 } from 'lucide-react';
import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Alert, AlertDescription, AlertTitle } from '~/components/ui/alert';
import { Badge } from '~/components/ui/badge';
import {
  BrandSelect,
  BrandSelectContent,
  BrandSelectItem,
  BrandSelectTrigger,
  SelectValue,
} from '~/components/ui/brand-select';
import { SecondaryButton } from '~/components/ui/buttons';
import { Input } from '~/components/ui/input';
import { Label } from '~/components/ui/label';
import { Switch } from '~/components/ui/switch';
import { ToggleGroup, ToggleGroupItem } from '~/components/ui/toggle-group';
import { UserAvatar } from '~/components/user/UserAvatar';
import { DisplayName } from '~/components/user/avatar';
import type { OrgFeatureAccess } from '~/features/org-features';
import { extractApiError } from '~/lib/apiError';
import { getLogger } from '~/lib/logger';
import { cn } from '~/lib/utils';
import { ContactRecordedStatus } from './ContactRecordedStatus';
import {
  relativeFromIso,
  reportPromoError,
  undoToastDescription,
  usePreviewOptions,
} from './feedback';
import {
  useCandidates,
  useResolveDiscordMember,
  useUndoPromoSend,
} from './queries';
import {
  DAYS_OPTIONS,
  MAX_POOL_N,
  isLinked,
  type CandidateFilters,
  type CandidateRow,
  type CandidateSource,
  type ContactSync,
  type LinkedCandidate,
} from './schemas';

const log = getLogger('CandidateList');

const POOL_OPTIONS = Array.from({ length: MAX_POOL_N }, (_, i) => i + 1);

const SOURCE_TABS: readonly { value: CandidateSource; label: string }[] = [
  { value: 'recent', label: 'Recent players' },
  { value: 'active', label: 'Active members' },
  { value: 'discord', label: 'New on Discord' },
];

const EMPTY_MESSAGE: Record<CandidateSource, string> = {
  recent:
    'No players match. Recent players without a linked Discord account are not listed.',
  active:
    'No members match. Members without a linked Discord account are not listed.',
  discord:
    'No new Discord members match. The organization needs a linked Discord server.',
};

function rowTestId(row: CandidateRow): string {
  return row.user_pk != null
    ? String(row.user_pk)
    : `discord-${row.discordId ?? ''}`;
}
const SEARCH_DEBOUNCE_MS = 300;

/**
 * SFG contact history arrives by import, so it can lag or miss contacts. The
 * notice says so; it never blocks messaging an otherwise eligible player.
 */
function ContactSyncNotice({ sync }: { sync: ContactSync }) {
  const previewOptions = usePreviewOptions();
  const imported = sync.last_receipt_imported_at;
  return (
    <Alert
      role="note"
      className="border-warning/40 bg-warning/10"
      data-testid="promo-contact-sync-warning"
    >
      <Info className="size-4" aria-hidden="true" />
      <AlertTitle>History may be incomplete</AlertTitle>
      <AlertDescription className="text-muted-foreground">
        Contacts recorded in SFG are ticked here once imported, and SFG may hold
        contacts that have not arrived yet. Players without a tick can still be
        messaged.
        {imported && (
          <span className="block" data-testid="promo-contact-sync-imported">
            Last SFG receipt imported{' '}
            {relativeFromIso(imported, previewOptions)}.
          </span>
        )}
      </AlertDescription>
    </Alert>
  );
}

export interface CandidateListProps {
  orgId: number;
  access: OrgFeatureAccess;
  eventId: number;
  filters: CandidateFilters;
  onFiltersChange: (filters: CandidateFilters) => void;
  selectedPk: number | null;
  onSelect: (row: LinkedCandidate) => void;
  /** A send shown elsewhere with its own undo; its row button is hidden to avoid duplicates. */
  hideUndoFor: number | null;
}

export function CandidateList({
  orgId,
  access,
  eventId,
  filters,
  onFiltersChange,
  selectedPk,
  onSelect,
  hideUndoFor,
}: CandidateListProps) {
  const { data, isLoading, isError, error } = useCandidates(
    orgId,
    access,
    eventId,
    filters,
  );
  const undo = useUndoPromoSend(orgId, access);
  const resolve = useResolveDiscordMember(orgId, access, eventId);
  const previewOptions = usePreviewOptions();
  const [search, setSearch] = useState(filters.q);

  useEffect(() => {
    if (search === filters.q) return;
    const timer = setTimeout(
      () => onFiltersChange({ ...filters, q: search }),
      SEARCH_DEBOUNCE_MS,
    );
    return () => clearTimeout(timer);
  }, [search, filters, onFiltersChange]);

  const copyDiscord = async (username: string): Promise<void> => {
    try {
      await navigator.clipboard.writeText(username);
      toast.success('Discord username copied');
    } catch {
      toast.error('Could not copy the username');
    }
  };

  const syncConfigured = data?.contact_sync.configured ?? false;

  const onUndo = (sendId: number): void => {
    undo.mutate(sendId, {
      onSuccess: (result) =>
        toast.success('Send undone', {
          description: undoToastDescription(result, syncConfigured),
        }),
      onError: (err) => {
        const message = reportPromoError(log, 'promo_undo_failed', err, {
          orgId,
          sendId,
        });
        toast.error(message || 'Could not undo the send');
      },
    });
  };

  const onMessage = (row: CandidateRow): void => {
    if (row.external_contact) return;
    if (isLinked(row)) {
      onSelect(row);
      return;
    }
    if (!row.discordId) return;
    resolve.mutate(row.discordId, {
      onSuccess: (resolved) => {
        if (resolved.external_contact) {
          toast.info('A contact with this player is already recorded in SFG');
          return;
        }
        if (isLinked(resolved)) onSelect(resolved);
      },
      onError: (err) => {
        const message = reportPromoError(
          log,
          'promo_resolve_member_failed',
          err,
          { orgId, eventId },
        );
        toast.error(message || 'Could not prepare this member');
      },
    });
  };

  const poolN = data?.n ?? filters.n;

  const detail = (row: CandidateRow): string | null => {
    if (filters.source === 'recent' && row.recent_count != null)
      return `Played ${row.recent_count} of the last ${poolN}`;
    if (filters.source === 'active' && row.last_active_at)
      return `Active ${relativeFromIso(row.last_active_at, previewOptions)}`;
    if (filters.source === 'discord' && row.discord_joined_at)
      return `Joined Discord ${relativeFromIso(row.discord_joined_at, previewOptions)}`;
    return null;
  };

  return (
    <section className="flex flex-col gap-3" data-testid="promo-candidate-list">
      <ToggleGroup
        type="single"
        variant="outline"
        size="sm"
        value={filters.source}
        onValueChange={(next) => {
          if (next)
            onFiltersChange({ ...filters, source: next as CandidateSource });
        }}
        aria-label="Who to show"
        className="flex-wrap justify-start"
        data-testid="promo-source"
      >
        {SOURCE_TABS.map((tab) => (
          <ToggleGroupItem
            key={tab.value}
            value={tab.value}
            data-testid={`promo-source-${tab.value}`}
          >
            {tab.label}
          </ToggleGroupItem>
        ))}
      </ToggleGroup>
      <div className="flex flex-wrap items-end gap-3">
        {filters.source === 'recent' ? (
          <div className="flex flex-col gap-1">
            <Label className="text-xs text-muted-foreground">
              Recent tournaments
            </Label>
            <BrandSelect
              value={String(filters.n)}
              onValueChange={(value) =>
                onFiltersChange({ ...filters, n: Number(value) })
              }
            >
              <BrandSelectTrigger
                className="w-24"
                aria-label="Recent tournaments"
                data-testid="promo-pool-n"
              >
                <SelectValue />
              </BrandSelectTrigger>
              <BrandSelectContent>
                {POOL_OPTIONS.map((n) => (
                  <BrandSelectItem
                    key={n}
                    value={String(n)}
                    data-testid={`promo-pool-n-${n}`}
                  >
                    {n}
                  </BrandSelectItem>
                ))}
              </BrandSelectContent>
            </BrandSelect>
          </div>
        ) : (
          <div className="flex flex-col gap-1">
            <Label className="text-xs text-muted-foreground">
              {filters.source === 'active' ? 'Active within' : 'Joined within'}
            </Label>
            <BrandSelect
              value={String(filters.days)}
              onValueChange={(value) =>
                onFiltersChange({ ...filters, days: Number(value) })
              }
            >
              <BrandSelectTrigger
                className="w-28"
                aria-label="Days"
                data-testid="promo-days"
              >
                <SelectValue />
              </BrandSelectTrigger>
              <BrandSelectContent>
                {DAYS_OPTIONS.map((days) => (
                  <BrandSelectItem
                    key={days}
                    value={String(days)}
                    data-testid={`promo-days-${days}`}
                  >
                    {days} days
                  </BrandSelectItem>
                ))}
              </BrandSelectContent>
            </BrandSelect>
          </div>
        )}
        <div className="flex items-center gap-2 min-h-11">
          <Switch
            id="promo-hide-signed-up"
            checked={filters.hideSignedUp}
            onCheckedChange={(checked) =>
              onFiltersChange({ ...filters, hideSignedUp: checked })
            }
            data-testid="promo-hide-signed-up"
          />
          <Label htmlFor="promo-hide-signed-up">Hide signed up</Label>
        </div>
        <div className="flex items-center gap-2 min-h-11">
          <Switch
            id="promo-hide-messaged"
            checked={filters.hideMessaged}
            onCheckedChange={(checked) =>
              onFiltersChange({ ...filters, hideMessaged: checked })
            }
            data-testid="promo-hide-messaged"
          />
          <Label htmlFor="promo-hide-messaged">Hide messaged</Label>
        </div>
        <Input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search players..."
          className="w-full sm:w-56"
          aria-label="Search players"
          data-testid="promo-search"
        />
      </div>

      {data?.contact_sync.configured && (
        <ContactSyncNotice sync={data.contact_sync} />
      )}
      {isLoading && (
        <p className="text-sm text-muted-foreground">Loading players...</p>
      )}
      {isError && (
        <p
          className="text-sm text-destructive"
          data-testid="promo-candidates-error"
        >
          {extractApiError(error) ?? 'Could not load players.'}
        </p>
      )}
      {data && data.rows.length === 0 && (
        <p
          className="text-sm text-muted-foreground"
          data-testid="promo-candidates-empty"
        >
          {EMPTY_MESSAGE[filters.source]}
        </p>
      )}

      <ul className="flex flex-col gap-2">
        {data?.rows.map((row) => {
          const last = row.last_messaged;
          const external = row.external_contact;
          const selected = row.user_pk != null && row.user_pk === selectedPk;
          const testId = rowTestId(row);
          const info = detail(row);
          return (
            <li
              key={testId}
              className={cn(
                'flex flex-wrap items-center gap-3 rounded-md border p-3',
                selected
                  ? 'border-primary bg-primary/10'
                  : 'border-border bg-base-900/40',
              )}
              data-testid={`promo-candidate-${testId}`}
            >
              <UserAvatar
                user={{ ...row, pk: row.user_pk ?? undefined }}
                size="sm"
              />
              <div className="flex min-w-0 flex-1 flex-col">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">{DisplayName(row)}</span>
                  {row.signed_up && (
                    <Badge variant="secondary">Signed up</Badge>
                  )}
                  {!isLinked(row) && (
                    <Badge variant="outline">No account yet</Badge>
                  )}
                </div>
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
                  {row.discordUsername && (
                    <span className="inline-flex items-center gap-1">
                      {/* eslint-disable-next-line draftforge/use-display-name -- the Discord @handle shown next to its copy button */}
                      @{row.discordUsername}
                      <SecondaryButton
                        type="button"
                        size="icon"
                        className="size-6"
                        onClick={() => copyDiscord(row.discordUsername!)}
                        aria-label="Copy Discord username"
                        data-testid={`promo-copy-discord-${testId}`}
                      >
                        <Copy className="size-3" />
                      </SecondaryButton>
                    </span>
                  )}
                  {info && <span>{info}</span>}
                  <ContactRecordedStatus
                    externalContact={external}
                    localLastMessaged={last}
                    testId={testId}
                  />
                </div>
              </div>
              <div className="flex items-center gap-2">
                {last?.can_undo && last.send_id !== hideUndoFor && (
                  <SecondaryButton
                    type="button"
                    size="sm"
                    onClick={() => onUndo(last.send_id)}
                    disabled={undo.isPending}
                    data-testid={`promo-undo-${last.send_id}`}
                  >
                    <Undo2 className="h-4 w-4 mr-1" />
                    Undo
                  </SecondaryButton>
                )}
                <SecondaryButton
                  type="button"
                  size="sm"
                  onClick={() => onMessage(row)}
                  disabled={
                    external != null || (!isLinked(row) && resolve.isPending)
                  }
                  aria-pressed={selected}
                  aria-describedby={
                    external ? `promo-message-blocked-${testId}` : undefined
                  }
                  data-testid={`promo-select-${testId}`}
                >
                  {selected ? 'Selected' : 'Message'}
                </SecondaryButton>
                {external && (
                  <span
                    id={`promo-message-blocked-${testId}`}
                    className="sr-only"
                  >
                    Contact recorded in SFG, so messaging is off for this
                    player.
                  </span>
                )}
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
