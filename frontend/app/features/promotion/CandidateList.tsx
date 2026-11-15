import { Copy, Undo2 } from 'lucide-react';
import { useEffect, useState } from 'react';
import { toast } from 'sonner';
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
import { UserAvatar } from '~/components/user/UserAvatar';
import type { OrgFeatureAccess } from '~/features/org-features';
import { extractApiError } from '~/lib/apiError';
import { getLogger } from '~/lib/logger';
import { cn } from '~/lib/utils';
import { candidateName } from './ComposePanel';
import {
  relativeFromIso,
  reportPromoError,
  usePreviewOptions,
} from './feedback';
import { useCandidates, useUndoPromoSend } from './queries';
import {
  MAX_POOL_N,
  type CandidateFilters,
  type CandidateRow,
} from './schemas';

const log = getLogger('CandidateList');

const POOL_OPTIONS = Array.from({ length: MAX_POOL_N }, (_, i) => i + 1);
const SEARCH_DEBOUNCE_MS = 300;

export interface CandidateListProps {
  orgId: number;
  access: OrgFeatureAccess;
  eventId: number;
  filters: CandidateFilters;
  onFiltersChange: (filters: CandidateFilters) => void;
  selectedPk: number | null;
  onSelect: (row: CandidateRow) => void;
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

  const onUndo = (sendId: number): void => {
    undo.mutate(sendId, {
      onSuccess: () => toast.success('Send undone'),
      onError: (err) => {
        const message = reportPromoError(log, 'promo_undo_failed', err, {
          orgId,
          sendId,
        });
        toast.error(message || 'Could not undo the send');
      },
    });
  };

  const poolN = data?.n ?? filters.n;

  return (
    <section className="flex flex-col gap-3" data-testid="promo-candidate-list">
      <div className="flex flex-wrap items-end gap-3">
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
          No players match. Recent players without a linked Discord account are
          not listed.
        </p>
      )}

      <ul className="flex flex-col gap-2">
        {data?.rows.map((row) => {
          const last = row.last_messaged;
          const selected = row.user_pk === selectedPk;
          return (
            <li
              key={row.user_pk}
              className={cn(
                'flex flex-wrap items-center gap-3 rounded-md border p-3',
                selected
                  ? 'border-primary bg-primary/10'
                  : 'border-border bg-base-900/40',
              )}
              data-testid={`promo-candidate-${row.user_pk}`}
            >
              <UserAvatar
                user={{
                  pk: row.user_pk,
                  username: row.username,
                  nickname: row.nickname,
                  avatarUrl: row.avatarUrl,
                  discordId: row.discordId,
                }}
                size="sm"
              />
              <div className="flex min-w-0 flex-1 flex-col">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">{candidateName(row)}</span>
                  {row.signed_up && (
                    <Badge variant="secondary">Signed up</Badge>
                  )}
                </div>
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
                  {row.discordUsername && (
                    <span className="inline-flex items-center gap-1">
                      @{row.discordUsername}
                      <SecondaryButton
                        type="button"
                        size="icon"
                        className="size-6"
                        onClick={() => copyDiscord(row.discordUsername!)}
                        aria-label="Copy Discord username"
                        data-testid={`promo-copy-discord-${row.user_pk}`}
                      >
                        <Copy className="size-3" />
                      </SecondaryButton>
                    </span>
                  )}
                  <span>
                    Played {row.recent_count} of the last {poolN}
                  </span>
                  {last && (
                    <span data-testid={`promo-last-messaged-${row.user_pk}`}>
                      Messaged by {last.by ?? 'someone'},{' '}
                      {relativeFromIso(last.sent_at, previewOptions)}
                    </span>
                  )}
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
                  onClick={() => onSelect(row)}
                  aria-pressed={selected}
                  data-testid={`promo-select-${row.user_pk}`}
                >
                  {selected ? 'Selected' : 'Message'}
                </SecondaryButton>
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
