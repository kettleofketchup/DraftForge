import { Info } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { GAME_LABEL, toGameType } from '~/components/game/constants';
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
import type { OrgFeatureAccess } from '~/features/org-features';
import { extractApiError } from '~/lib/apiError';
import { getLogger } from '~/lib/logger';
import {
  relativeFromIso,
  reportPromoError,
  undoToastDescription,
  usePreviewOptions,
} from './feedback';
import { parseMmrBound, validateMmrRange } from './mmrFilter';
import type { ComposeMode } from './promotionColumns';
import { PromotionTable } from './PromotionTable';
import { useCandidates, useUndoPromoSend } from './queries';
import {
  DAYS_OPTIONS,
  DEFAULT_CANDIDATE_FILTERS,
  MAX_POOL_N,
  type CandidateFilters,
  type CandidateRow,
  type CandidateSource,
  type ContactSync,
} from './schemas';

const log = getLogger('CandidateList');

const POOL_OPTIONS = Array.from({ length: MAX_POOL_N }, (_, i) => i + 1);

const SOURCE_TABS: readonly {
  value: CandidateSource;
  label: string;
  hint: string;
}[] = [
  {
    value: 'recent',
    label: 'Recent players',
    hint: "Played in the org's latest tournaments",
  },
  {
    value: 'active',
    label: 'Active members',
    hint: 'Signed up or played lately',
  },
  {
    value: 'discord',
    label: 'New on Discord',
    hint: 'Joined the Discord server lately',
  },
];

const EMPTY_MESSAGE: Record<CandidateSource, string> = {
  recent:
    'No players match. Recent players without a linked Discord account are not listed.',
  active:
    'No members match. Members without a linked Discord account are not listed.',
  discord:
    'No new Discord members match. The organization needs a linked Discord server.',
};

const DEBOUNCE_MS = 300;

/** Commits `value` through `commit` once it stops changing. */
function useDebouncedCommit<T>(
  value: T,
  committed: T,
  commit: (value: T) => void,
): void {
  useEffect(() => {
    if (Object.is(value, committed)) return;
    const timer = setTimeout(() => commit(value), DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [value, committed, commit]);
}

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
  onCompose: (row: CandidateRow, mode: ComposeMode) => void;
  /** Row whose Discord member is being prepared for a message. */
  pendingRowId: string | null;
  /** A send shown in the open composer with its own undo; its row action is hidden. */
  hideUndoFor: number | null;
}

function activeFilterLabels(
  filters: CandidateFilters,
  gameLabel: string,
): { key: string; label: string }[] {
  const labels: { key: string; label: string }[] = [];
  if (filters.source === 'recent')
    labels.push({ key: 'window', label: `Last ${filters.n} tournaments` });
  else labels.push({ key: 'window', label: `Last ${filters.days} days` });
  if (filters.minMmr != null && filters.maxMmr != null)
    labels.push({
      key: 'mmr',
      label: `${gameLabel} MMR ${filters.minMmr}–${filters.maxMmr}`,
    });
  else if (filters.minMmr != null)
    labels.push({ key: 'mmr', label: `${gameLabel} MMR ≥ ${filters.minMmr}` });
  else if (filters.maxMmr != null)
    labels.push({ key: 'mmr', label: `${gameLabel} MMR ≤ ${filters.maxMmr}` });
  labels.push({
    key: 'signed-up',
    label: filters.hideSignedUp ? 'Hiding signed up' : 'Showing signed up',
  });
  labels.push({
    key: 'messaged',
    label: filters.hideMessaged ? 'Hiding messaged' : 'Showing messaged',
  });
  if (filters.q) labels.push({ key: 'search', label: `Search “${filters.q}”` });
  return labels;
}

function isDefaultFilters(filters: CandidateFilters): boolean {
  const d = DEFAULT_CANDIDATE_FILTERS;
  return (
    filters.n === d.n &&
    filters.days === d.days &&
    filters.hideSignedUp === d.hideSignedUp &&
    filters.hideMessaged === d.hideMessaged &&
    filters.q === d.q &&
    filters.minMmr === d.minMmr &&
    filters.maxMmr === d.maxMmr
  );
}

export function CandidateList({
  orgId,
  access,
  eventId,
  filters,
  onFiltersChange,
  onCompose,
  pendingRowId,
  hideUndoFor,
}: CandidateListProps) {
  const { data, isLoading, isError, error, isFetching } = useCandidates(
    orgId,
    access,
    eventId,
    filters,
  );
  const undo = useUndoPromoSend(orgId, access);
  const previewOptions = usePreviewOptions();
  const [search, setSearch] = useState(filters.q);
  const [minText, setMinText] = useState(filters.minMmr?.toString() ?? '');
  const [maxText, setMaxText] = useState(filters.maxMmr?.toString() ?? '');

  const commitSearch = useCallback(
    (q: string) => onFiltersChange({ ...filters, q }),
    [filters, onFiltersChange],
  );
  useDebouncedCommit(search, filters.q, commitSearch);

  const minMmr = parseMmrBound(minText);
  const maxMmr = parseMmrBound(maxText);
  const mmrError = validateMmrRange(minMmr, maxMmr);
  const commitMmr = useCallback(
    (range: string) => {
      const [low, high] = range.split(':');
      onFiltersChange({
        ...filters,
        minMmr: low ? Number(low) : null,
        maxMmr: high ? Number(high) : null,
      });
    },
    [filters, onFiltersChange],
  );
  const wantedRange =
    mmrError == null
      ? `${minMmr.value ?? ''}:${maxMmr.value ?? ''}`
      : `${filters.minMmr ?? ''}:${filters.maxMmr ?? ''}`;
  useDebouncedCommit(
    wantedRange,
    `${filters.minMmr ?? ''}:${filters.maxMmr ?? ''}`,
    commitMmr,
  );

  const resetFilters = (): void => {
    setSearch('');
    setMinText('');
    setMaxText('');
    onFiltersChange({ ...DEFAULT_CANDIDATE_FILTERS, source: filters.source });
  };

  const copyDiscord = useCallback(async (username: string): Promise<void> => {
    try {
      await navigator.clipboard.writeText(username);
      toast.success('Discord username copied');
    } catch {
      toast.error('Could not copy the username');
    }
  }, []);

  const syncConfigured = data?.contact_sync.configured ?? false;

  const onUndo = useCallback(
    (sendId: number): void => {
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
    },
    [undo, orgId, syncConfigured],
  );

  const gameLabel = data ? GAME_LABEL[toGameType(data.game_type)] : 'Game';
  const mmrBounded = filters.minMmr != null || filters.maxMmr != null;
  const rows = data?.rows ?? [];
  const audience = SOURCE_TABS.find((t) => t.value === filters.source)!;

  return (
    <section
      className="flex w-full flex-col gap-4"
      data-testid="promo-candidate-list"
    >
      <ToggleGroup
        type="single"
        variant="outline"
        value={filters.source}
        onValueChange={(next) => {
          if (next)
            onFiltersChange({ ...filters, source: next as CandidateSource });
        }}
        aria-label="Audience"
        className="grid w-full grid-cols-1 gap-2 sm:grid-cols-3"
        data-testid="promo-source"
      >
        {SOURCE_TABS.map((tab) => (
          <ToggleGroupItem
            key={tab.value}
            value={tab.value}
            className="h-auto min-h-11 flex-col items-start gap-0.5 rounded-md border px-4 py-3 text-left whitespace-normal first:rounded-md last:rounded-md data-[state=on]:border-primary data-[state=on]:bg-primary/15 data-[state=on]:text-foreground data-[variant=outline]:border-l"
            data-testid={`promo-source-${tab.value}`}
          >
            <span className="text-base font-semibold">{tab.label}</span>
            <span className="text-xs font-normal text-muted-foreground">
              {tab.hint}
            </span>
          </ToggleGroupItem>
        ))}
      </ToggleGroup>

      <div
        className="grid grid-cols-2 items-end gap-3 rounded-lg border border-border bg-base-900/40 p-3 sm:flex sm:flex-wrap"
        data-testid="promo-filters"
      >
        {filters.source === 'recent' ? (
          <div className="flex flex-col gap-1">
            <Label htmlFor="promo-pool-n" className="text-xs">
              Recent tournaments
            </Label>
            <BrandSelect
              value={String(filters.n)}
              onValueChange={(value) =>
                onFiltersChange({ ...filters, n: Number(value) })
              }
            >
              <BrandSelectTrigger
                id="promo-pool-n"
                className="min-h-11 w-full sm:min-h-9 sm:w-24"
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
            <Label htmlFor="promo-days" className="text-xs">
              {filters.source === 'active' ? 'Active within' : 'Joined within'}
            </Label>
            <BrandSelect
              value={String(filters.days)}
              onValueChange={(value) =>
                onFiltersChange({ ...filters, days: Number(value) })
              }
            >
              <BrandSelectTrigger
                id="promo-days"
                className="min-h-11 w-full sm:min-h-9 sm:w-28"
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
        <div className="col-span-2 grid grid-cols-2 gap-3 sm:contents">
          <div className="flex flex-col gap-1">
            <Label htmlFor="promo-min-mmr" className="text-xs">
              Min {gameLabel} MMR
            </Label>
            <Input
              id="promo-min-mmr"
              type="number"
              inputMode="numeric"
              min={0}
              step={100}
              value={minText}
              onChange={(e) => setMinText(e.target.value)}
              placeholder="Any"
              aria-invalid={minMmr.error != null || mmrError != null}
              aria-describedby="promo-mmr-help"
              className="min-h-11 w-full sm:min-h-9 sm:w-28"
              data-testid="promo-min-mmr"
            />
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="promo-max-mmr" className="text-xs">
              Max {gameLabel} MMR
            </Label>
            <Input
              id="promo-max-mmr"
              type="number"
              inputMode="numeric"
              min={0}
              step={100}
              value={maxText}
              onChange={(e) => setMaxText(e.target.value)}
              placeholder="Any"
              aria-invalid={maxMmr.error != null || mmrError != null}
              aria-describedby="promo-mmr-help"
              className="min-h-11 w-full sm:min-h-9 sm:w-28"
              data-testid="promo-max-mmr"
            />
          </div>
        </div>
        <div className="col-span-2 flex min-h-11 items-center gap-2 sm:col-span-1">
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
        <div className="col-span-2 flex min-h-11 items-center gap-2 sm:col-span-1">
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
        <p
          id="promo-mmr-help"
          className="col-span-2 text-xs text-muted-foreground sm:basis-full"
          data-testid="promo-mmr-help"
        >
          {mmrError ? (
            <span className="text-destructive" data-testid="promo-mmr-error">
              {mmrError}
            </span>
          ) : mmrBounded ? (
            <span data-testid="promo-mmr-unknown-hint">
              Players without an org {gameLabel} MMR (shown as Unknown),
              including Discord members without an account, are hidden while an
              MMR filter is set.
            </span>
          ) : (
            `MMR is this organization's ${gameLabel} rating; Unknown means none is set.`
          )}
        </p>
      </div>

      <div
        className="flex flex-wrap items-center gap-2"
        data-testid="promo-active-filters"
        aria-label="Active filters"
      >
        <Badge variant="default">{audience.label}</Badge>
        {activeFilterLabels(filters, gameLabel).map((f) => (
          <Badge
            key={f.key}
            variant="outline"
            data-testid={`promo-active-filter-${f.key}`}
          >
            {f.label}
          </Badge>
        ))}
        {!isDefaultFilters(filters) && (
          <SecondaryButton
            type="button"
            size="sm"
            className="min-h-11 sm:min-h-8"
            onClick={resetFilters}
            data-testid="promo-filters-reset"
          >
            Reset filters
          </SecondaryButton>
        )}
      </div>

      {data?.contact_sync.configured && (
        <ContactSyncNotice sync={data.contact_sync} />
      )}
      {isError && (
        <p
          className="text-sm text-destructive"
          data-testid="promo-candidates-error"
        >
          {extractApiError(error) ?? 'Could not load players.'}
        </p>
      )}

      <PromotionTable
        rows={rows}
        source={filters.source}
        poolN={data?.n ?? filters.n}
        previewOptions={previewOptions}
        onCompose={onCompose}
        onUndo={onUndo}
        onCopyHandle={copyDiscord}
        pendingRowId={pendingRowId}
        undoPending={undo.isPending}
        hideUndoFor={hideUndoFor}
        search={{
          value: search,
          onChange: setSearch,
          label: 'Search players',
          placeholder: 'Name, Discord or guild nickname',
        }}
        toolbarStart={
          <span data-testid="promo-candidate-count" aria-live="polite">
            {isLoading
              ? 'Loading players...'
              : `${rows.length} ${rows.length === 1 ? 'player' : 'players'}${isFetching ? ' · updating...' : ''}`}
          </span>
        }
        emptyMessage={
          isLoading ? (
            'Loading players...'
          ) : (
            <span data-testid="promo-candidates-empty">
              {mmrBounded
                ? `No players with a known ${gameLabel} MMR in this range. Clear the MMR filter to include Unknown.`
                : EMPTY_MESSAGE[filters.source]}
            </span>
          )
        }
      />
    </section>
  );
}
