import { useEffect, useRef, useState } from 'react';
import { useUserStore } from '~/store/userStore';

export interface MemberAccessSource {
  can_view_members?: boolean;
  members_viewer_pk?: number | null;
}

export interface MemberAccess {
  /** Last answer the backend gave; false before the first one. */
  canView: boolean;
  /** The answer was computed for the signed-in viewer, so it is safe to act on. */
  settled: boolean;
}

/**
 * Reads the per-viewer `can_view_members` flag off an org or league detail
 * payload. Login and logout happen without a reload, so when the viewer
 * changes and the payload was computed for someone else, `onStale` runs to
 * drop member data and refetch.
 */
export function useMemberAccess(
  source: MemberAccessSource | null | undefined,
  onStale: () => void,
): MemberAccess {
  const viewerPk = useUserStore((s) => s.currentUser?.pk ?? null);
  const flag = source?.can_view_members;
  const flagViewerPk = source?.members_viewer_pk ?? null;

  const [lastKnown, setLastKnown] = useState(false);
  if (flag !== undefined && flag !== lastKnown) setLastKnown(flag);

  const onStaleRef = useRef(onStale);
  useEffect(() => {
    onStaleRef.current = onStale;
  }, [onStale]);

  const prevViewerPk = useRef(viewerPk);
  useEffect(() => {
    if (prevViewerPk.current === viewerPk) return;
    prevViewerPk.current = viewerPk;
    if (flag !== undefined && flagViewerPk !== viewerPk) onStaleRef.current();
  }, [viewerPk, flag, flagViewerPk]);

  return {
    canView: flag ?? lastKnown,
    settled: flag !== undefined && flagViewerPk === viewerPk,
  };
}
