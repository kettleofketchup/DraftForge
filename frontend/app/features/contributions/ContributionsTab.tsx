import { useMemo, useState } from 'react';
import {
  BrandSelect,
  BrandSelectContent,
  BrandSelectItem,
  BrandSelectTrigger,
  SelectValue,
} from '~/components/ui/brand-select';
import type { OrgFeatureAccess } from '~/features/org-features';
import { extractApiError } from '~/lib/apiError';
import { Leaderboard } from './Leaderboard';
import { MemberBreakdown } from './MemberBreakdown';
import { useLeaderboard } from './queries';
import { ALL_TIME } from './schemas';
import { periodOptions } from './timezone';

export interface ContributionsTabProps {
  orgId: number;
  timeZone: string | undefined;
  membersPrivate: boolean;
  access: OrgFeatureAccess;
}

export function ContributionsTab({ orgId, timeZone, membersPrivate, access }: ContributionsTabProps) {
  const [period, setPeriod] = useState<string>(ALL_TIME);
  const [selected, setSelected] = useState<number | null>(null);
  const options = useMemo(() => periodOptions(timeZone), [timeZone]);
  const { data, isLoading, isError, error } = useLeaderboard(orgId, access, period);

  const canOpen = (orgUserPk: number): boolean =>
    data != null && (data.rows_visible || data.own_row?.org_user_pk === orgUserPk);

  return (
    <div className="flex flex-col gap-4" data-testid="contributions-tab">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-xl font-semibold">Contributions</h2>
        <BrandSelect
          value={period}
          onValueChange={(value) => {
            setPeriod(value);
          }}
        >
          <BrandSelectTrigger
            className="min-w-44"
            aria-label="Period"
            data-testid="contributions-period-select"
          >
            <SelectValue />
          </BrandSelectTrigger>
          <BrandSelectContent>
            {options.map((option) => (
              <BrandSelectItem
                key={option.value}
                value={option.value}
                data-testid={`contributions-period-${option.value}`}
              >
                {option.label}
              </BrandSelectItem>
            ))}
          </BrandSelectContent>
        </BrandSelect>
      </div>

      {isLoading && <div className="py-6 text-center text-muted-foreground">Loading contributions...</div>}
      {isError && (
        <div className="text-destructive" data-testid="contributions-error">
          {extractApiError(error) ?? 'Could not load contributions.'}
        </div>
      )}

      {data && (
        <div className="grid gap-4 lg:grid-cols-2">
          <Leaderboard
            data={data}
            viewerPk={access.viewerPk}
            membersPrivate={membersPrivate}
            onSelectMember={(pk) => {
              if (canOpen(pk)) setSelected(pk);
            }}
          />
          {selected != null && canOpen(selected) && (
            <MemberBreakdown
              orgId={orgId}
              orgUserPk={selected}
              period={period}
              timeZone={timeZone}
              access={access}
              onClose={() => setSelected(null)}
            />
          )}
        </div>
      )}
    </div>
  );
}
