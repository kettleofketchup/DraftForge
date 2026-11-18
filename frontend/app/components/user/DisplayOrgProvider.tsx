import { type ReactNode, useLayoutEffect, useState } from 'react';

import { useDisplayOrgStore } from '~/store/displayOrgStore';

export { useDisplayOrgId } from '~/store/displayOrgStore';

type Props = { orgId: number | null | undefined; children: ReactNode };

function DisplayOrgScope({
  orgId,
  children,
}: {
  orgId: number | null;
  children: ReactNode;
}) {
  const [pushed, setPushed] = useState(false);
  useLayoutEffect(() => {
    const token = useDisplayOrgStore.getState().push(orgId);
    setPushed(true);
    return () => useDisplayOrgStore.getState().pop(token);
  }, [orgId]);
  return pushed ? children : null;
}

/** Sets the org that DisplayName and UserAvatar resolve server nicknames against; children mount once it is set. */
export function DisplayOrgProvider({ orgId, children }: Props) {
  const id = orgId ?? null;
  return (
    <DisplayOrgScope key={id ?? 'none'} orgId={id}>
      {children}
    </DisplayOrgScope>
  );
}
