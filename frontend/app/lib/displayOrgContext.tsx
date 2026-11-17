import { createContext, type ReactNode } from 'react';

export const DisplayOrgContext = createContext<number | null>(null);

export function DisplayOrgProvider({
  orgId,
  children,
}: {
  orgId: number | null | undefined;
  children: ReactNode;
}) {
  return (
    <DisplayOrgContext.Provider value={orgId ?? null}>
      {children}
    </DisplayOrgContext.Provider>
  );
}
