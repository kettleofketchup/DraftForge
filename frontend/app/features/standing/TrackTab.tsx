import { Lock } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import {
  BrandSelect,
  BrandSelectContent,
  BrandSelectItem,
  BrandSelectTrigger,
  SelectValue,
} from '~/components/ui/brand-select';
import type { OrgFeatureAccess } from '~/features/org-features';
import { extractApiError } from '~/lib/apiError';
import { getLogger } from '~/lib/logger';
import { MetricSwitcher } from './MetricSwitcher';
import { panelFor } from './panels';
import { ALL_TIME, periodOptions } from './periods';
import { useStandingLeaderboard } from './queries';
import { defaultMetric, type TrackInfo } from './schemas';
import { StandingLeaderboard } from './StandingLeaderboard';
import type { StandingTableRow } from './standingLeaderboardColumns';

const log = getLogger('TrackTab');

export interface TrackTabProps {
  orgId: number;
  track: TrackInfo;
  timeZone: string | undefined;
  membersPrivate: boolean;
  access: OrgFeatureAccess;
}

interface Selection {
  orgUserPk: number;
  own: boolean;
}

export function TrackTab({
  orgId,
  track,
  timeZone,
  membersPrivate,
  access,
}: TrackTabProps) {
  const panel = panelFor(track.key);
  const [metricKey, setMetricKey] = useState<string>(
    () => defaultMetric(track).key,
  );
  const [period, setPeriod] = useState<string>(ALL_TIME);
  const [picked, setPicked] = useState<Selection | null>(null);
  const [dismissed, setDismissed] = useState(false);
  const metric =
    track.metrics.find((m) => m.key === metricKey) ?? defaultMetric(track);
  const options = useMemo(() => periodOptions(timeZone), [timeZone]);
  const { data, isLoading, isError, error } = useStandingLeaderboard(
    orgId,
    access,
    track,
    metric,
    period,
  );

  useEffect(() => {
    if (isError)
      log.error('standing leaderboard failed to load', {
        orgId,
        track: track.key,
        metric: metric.key,
        error: extractApiError(error),
      });
  }, [isError, error, orgId, track.key, metric.key]);

  if (!panel) return null;
  const prefix = panel.tabValue;

  const canOpenRow = (row: StandingTableRow): boolean =>
    data != null &&
    panel.canOpen({ own: row.own, rowsVisible: data.rows_visible, access });

  const ownRow = data?.own_row ?? null;
  const selected: Selection | null =
    picked ??
    (panel.openOwnByDefault && !dismissed && ownRow
      ? { orgUserPk: ownRow.member.org_user_pk, own: true }
      : null);
  const showDetail =
    selected != null &&
    data != null &&
    panel.canOpen({
      own: selected.own,
      rowsVisible: data.rows_visible,
      access,
    });
  const Detail = panel.Detail;
  const Admin = panel.Admin;
  const HeaderExtra = panel.HeaderExtra;
  const Banner = panel.Banner;

  return (
    <div className="flex flex-col gap-4" data-testid={`${prefix}-tab`}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-xl font-semibold">{track.label}</h2>
        <div className="flex flex-wrap items-center gap-3">
          <MetricSwitcher
            track={track}
            value={metric.key}
            onChange={setMetricKey}
          />
          {HeaderExtra && <HeaderExtra />}
          {metric.periodic && (
            <BrandSelect value={period} onValueChange={setPeriod}>
              <BrandSelectTrigger
                className="min-w-44"
                aria-label="Period"
                data-testid={`${prefix}-period-select`}
              >
                <SelectValue />
              </BrandSelectTrigger>
              <BrandSelectContent>
                {options.map((option) => (
                  <BrandSelectItem
                    key={option.value}
                    value={option.value}
                    data-testid={`${prefix}-period-${option.value}`}
                  >
                    {option.label}
                  </BrandSelectItem>
                ))}
              </BrandSelectContent>
            </BrandSelect>
          )}
        </div>
      </div>

      {!track.board_open && (
        <p
          className="flex items-center gap-2 text-sm text-muted-foreground"
          data-testid={`${prefix}-self-only`}
        >
          <Lock className="h-4 w-4" />
          This organization keeps its {track.label} ranking private.
        </p>
      )}

      {Banner && <Banner orgId={orgId} timeZone={timeZone} access={access} />}

      {isLoading && (
        <div className="py-6 text-center text-muted-foreground">
          Loading {track.label.toLowerCase()}...
        </div>
      )}
      {isError && (
        <div className="text-destructive" data-testid={`${prefix}-error`}>
          {extractApiError(error) ??
            `Could not load ${track.label.toLowerCase()}.`}
        </div>
      )}

      {data && (
        <div className="grid gap-4 lg:grid-cols-2">
          <StandingLeaderboard
            board={data}
            testIdPrefix={prefix}
            sampleLabel={panel.sampleLabel(metric.key)}
            totalUnit={panel.totalUnit}
            emptyLabel={panel.emptyLabel(metric.periodic)}
            boardOpen={track.board_open}
            viewerPk={access.viewerPk}
            membersPrivate={membersPrivate}
            canOpen={canOpenRow}
            onOpen={(row) => {
              setDismissed(false);
              setPicked({ orgUserPk: row.member.org_user_pk, own: row.own });
            }}
          />
          {showDetail && (
            <Detail
              key={selected.orgUserPk}
              orgId={orgId}
              orgUserPk={selected.orgUserPk}
              own={selected.own}
              period={period}
              timeZone={timeZone}
              access={access}
              onClose={() => {
                setPicked(null);
                setDismissed(true);
              }}
            />
          )}
        </div>
      )}

      {Admin && <Admin orgId={orgId} timeZone={timeZone} access={access} />}
    </div>
  );
}
