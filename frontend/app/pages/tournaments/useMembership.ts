import { useEffect, useRef, useState } from 'react';
import { useUserStore } from '~/store/userStore';

export interface Membership {
  memberOrgIds: number[] | undefined;
  isLoggedIn: boolean;
  membershipPending: boolean;
}

export function useMembership(): Membership {
  const status = useUserStore((s) => s.currentUserStatus);
  const pk = useUserStore((s) => s.currentUser?.pk);
  const memberOrgIds = useUserStore((s) => s.currentUser?.member_organization_ids);
  const getCurrentUser = useUserStore((s) => s.getCurrentUser);
  const refetchStarted = useRef(false);
  const [membershipRefetchSettled, setMembershipRefetchSettled] = useState(false);

  useEffect(() => {
    if (useUserStore.getState().currentUserStatus === 'unknown') {
      void getCurrentUser();
    }
  }, [getCurrentUser]);

  useEffect(() => {
    if (status !== 'resolved' || !pk || memberOrgIds !== undefined) return;
    if (refetchStarted.current) return;
    refetchStarted.current = true;
    void Promise.resolve(getCurrentUser()).finally(() =>
      setMembershipRefetchSettled(true),
    );
  }, [status, pk, memberOrgIds, getCurrentUser]);

  const membershipPending =
    status !== 'resolved' ||
    (Boolean(pk) && memberOrgIds === undefined && !membershipRefetchSettled);

  return { memberOrgIds, isLoggedIn: Boolean(pk), membershipPending };
}
