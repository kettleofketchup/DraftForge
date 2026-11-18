import { create } from 'zustand';

type Frame = { token: number; orgId: number | null };

export interface DisplayOrgState {
  stack: Frame[];
  /** Org that names resolve against: the most recently mounted provider. Sibling providers with different orgs are not supported. */
  orgId: number | null;
  push(orgId: number | null): number;
  pop(token: number): void;
}

let nextToken = 0;

const topOrg = (stack: Frame[]): number | null =>
  stack.length ? stack[stack.length - 1].orgId : null;

export const useDisplayOrgStore = create<DisplayOrgState>((set, get) => ({
  stack: [],
  orgId: null,
  push(orgId) {
    const token = ++nextToken;
    const stack = [...get().stack, { token, orgId }];
    set({ stack, orgId: topOrg(stack) });
    return token;
  },
  pop(token) {
    const stack = get().stack.filter((f) => f.token !== token);
    if (stack.length === get().stack.length) return;
    set({ stack, orgId: topOrg(stack) });
  },
}));

export function useDisplayOrgId(): number | null {
  return useDisplayOrgStore((s) => s.orgId);
}
