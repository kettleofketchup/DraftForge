import { useShallow } from 'zustand/react/shallow';
import { matchesUserQuery, type NameSource } from '~/lib/userDisplayName';
import { useUserCacheStore } from '~/store/userCacheStore';

export type OrgNicknameMap = Record<number, string | null>;

const EMPTY: OrgNicknameMap = {};

export function useOrgNicknames(
  pks: readonly (number | null | undefined)[],
  orgId: number | null | undefined,
): OrgNicknameMap {
  return useUserCacheStore(
    useShallow((s) => {
      if (typeof orgId !== 'number') return EMPTY;
      const rec: OrgNicknameMap = {};
      for (const pk of pks) {
        if (typeof pk !== 'number') continue;
        rec[pk] = s.entities[pk]?.orgNicknames?.[orgId] ?? null;
      }
      return rec;
    }),
  );
}

export function withOrgNickname<T extends NameSource>(
  user: T,
  orgId: number | null | undefined,
  nicknames: OrgNicknameMap,
): T {
  if (typeof orgId !== 'number') return user;
  const own = user.orgNicknames;
  const nick =
    own && Object.prototype.hasOwnProperty.call(own, orgId)
      ? own[orgId]
      : typeof user.pk === 'number'
        ? (nicknames[user.pk] ?? null)
        : null;
  return { ...user, orgNicknames: { ...own, [orgId]: nick } };
}

export function matchesUserQueryIn(
  user: NameSource,
  q: string,
  orgId: number | null | undefined,
  nicknames: OrgNicknameMap,
): boolean {
  const scoped = typeof orgId === 'number' ? orgId : null;
  return matchesUserQuery(withOrgNickname(user, orgId, nicknames), q, scoped);
}
