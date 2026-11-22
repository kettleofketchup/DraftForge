import { useCallback } from 'react';
import type { OrgFeatureAccess } from '~/features/org-features';
import { eventConductEnabled } from './eventConduct';
import { useForecast } from './queries';
import type { ForecastMember } from './schemas';

export type ConductMemberLookup = (
  userPk: number,
) => ForecastMember | undefined;

export interface EventConduct {
  enabled: boolean;
  memberFor: ConductMemberLookup;
}

export function useEventConduct(
  event:
    | {
        id: number;
        organization?: number | null;
        user_can_manage?: boolean | null;
      }
    | null
    | undefined,
  org: Parameters<typeof eventConductEnabled>[1],
  access: OrgFeatureAccess,
): EventConduct {
  const enabled = eventConductEnabled(event, org, access);
  const { data } = useForecast(
    event?.organization ?? 0,
    access,
    event?.id ?? 0,
    enabled,
  );
  const members = enabled ? data?.members : undefined;
  const memberFor = useCallback<ConductMemberLookup>(
    (userPk) => members?.[String(userPk)],
    [members],
  );
  return { enabled, memberFor };
}
