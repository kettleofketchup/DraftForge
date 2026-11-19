import { Lock } from 'lucide-react';
import { useEffect, useState } from 'react';
import type { OrgFeatureAccess } from '~/features/org-features';
import { extractApiError } from '~/lib/apiError';
import { getLogger } from '~/lib/logger';
import { ConductLeaderboard } from './ConductLeaderboardTable';
import { MemberConductHistory } from './MemberConductHistory';
import { useConductLeaderboard } from './queries';

const log = getLogger('ConductTab');

export interface ConductTabProps {
  orgId: number;
  timeZone: string | undefined;
  membersPrivate: boolean;
  access: OrgFeatureAccess;
}

export function ConductTab({
  orgId,
  timeZone,
  membersPrivate,
  access,
}: ConductTabProps) {
  const [selectedPk, setSelectedPk] = useState<number | null>(null);
  const { data, isLoading, isError, error } = useConductLeaderboard(
    orgId,
    access,
  );
  const fullMode = access.canViewConduct;
  const isStaff = access.canViewConductDetails;
  const ownPk = data?.own_row?.member.org_user_pk ?? null;
  const historyPk = (fullMode ? selectedPk : null) ?? ownPk;

  useEffect(() => {
    if (isError)
      log.error('conduct leaderboard failed to load', { orgId, error });
  }, [isError, error, orgId]);

  const history =
    historyPk != null ? (
      <MemberConductHistory
        key={historyPk}
        orgId={orgId}
        access={access}
        orgUserPk={historyPk}
        timeZone={timeZone}
      />
    ) : null;

  return (
    <div className="flex flex-col gap-4" data-testid="conduct-tab">
      <h2 className="text-xl font-semibold">Conduct</h2>

      {isLoading && (
        <div className="py-6 text-center text-muted-foreground">
          Loading attendance...
        </div>
      )}
      {isError && (
        <div className="text-destructive" data-testid="conduct-error">
          {extractApiError(error) ?? 'Could not load attendance.'}
        </div>
      )}

      {data && fullMode && (
        <div className="grid gap-4 lg:grid-cols-2">
          <ConductLeaderboard
            data={data}
            viewerPk={access.viewerPk}
            membersPrivate={membersPrivate}
            selectedPk={historyPk}
            canSelect={isStaff}
            onSelect={setSelectedPk}
          />
          {history ??
            (isStaff && (
              <p
                className="text-sm text-muted-foreground"
                data-testid="conduct-history-prompt"
              >
                Select a member to see their attendance history.
              </p>
            ))}
        </div>
      )}

      {data && !fullMode && (
        <div className="flex flex-col gap-4">
          <p
            className="flex items-center gap-2 text-sm text-muted-foreground"
            data-testid="conduct-self-only"
          >
            <Lock className="size-4" />
            This organization keeps its attendance ranking private.
          </p>
          {history}
        </div>
      )}
    </div>
  );
}
