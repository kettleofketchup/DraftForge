import { z } from 'zod';
import type { FieldNamesMarkedBoolean } from 'react-hook-form';
import type { LeagueType } from '~/components/league/schemas';
import type { OrganizationType } from '~/components/organization/schemas';
import type { UserClassType, UserType } from '~/components/user/types';
import {
  useIsLeagueAdmin,
  useIsOrganizationStaff,
  useIsSuperuser,
} from '~/hooks/usePermissions';
import { updateOrgUser } from '~/components/api/api';
import { GAME_TYPE } from '~/components/game/constants';
import { selectPositions } from '~/store/selectPositions';
import { useUserCacheStore } from '~/store/userCacheStore';

// Dota positions use a 0-5 self-rating scale: 0=hidden, 1=favorite, 5=avoid.
const PositionFieldSchema = z.coerce.number().int().min(0).max(5);

export const EditUserSchema = z.object({
  nickname: z.string().trim().min(2).max(100).nullable(),
  steam_account_id: z.coerce.number().int().min(0).nullable(),
  positions: z.object({
    carry: PositionFieldSchema,
    mid: PositionFieldSchema,
    offlane: PositionFieldSchema,
    soft_support: PositionFieldSchema,
    hard_support: PositionFieldSchema,
  }),
  mmr: z.coerce.number().int().min(0).nullable().optional(),
});

export type EditUserInput = z.infer<typeof EditUserSchema>;

export type EditUserScope =
  | { kind: 'org'; organization: OrganizationType }
  | { kind: 'league'; league: LeagueType; organization?: OrganizationType }
  | { kind: 'global' };

export type EditableField = keyof EditUserInput;

// Coerce missing-or-empty string fields to null so Zod's `.nullable()`
// branch accepts them (an empty string would otherwise hit the .min(2)
// validator and block submission for users with no Discord nickname).
function emptyToNull(v: string | null | undefined): string | null {
  if (v == null) return null;
  return v === '' ? null : v;
}

export function buildDefaults(
  user: UserClassType,
  scope: EditUserScope,
): EditUserInput {
  // Non-reactive form-default read: route user-wide positions through the
  // gameType-aware selector over the list-populated entity adapter. Explicit
  // GAME_TYPE.DOTA2 (positions are Dota-scoped) since this builder runs outside
  // any game-context provider. Fall back to the passed user.positions when the
  // user isn't in the cache yet.
  const positions =
    (user.pk != null
      ? selectPositions(useUserCacheStore.getState(), user.pk, GAME_TYPE.DOTA2)
      : undefined) ?? user.positions;
  const base: Omit<EditUserInput, 'mmr'> = {
    nickname: emptyToNull(user.nickname),
    steam_account_id: user.steam_account_id ?? null,
    positions: {
      carry: positions?.carry ?? 0,
      mid: positions?.mid ?? 0,
      offlane: positions?.offlane ?? 0,
      soft_support: positions?.soft_support ?? 0,
      hard_support: positions?.hard_support ?? 0,
    },
  };
  return scope.kind === 'global' ? base : { ...base, mmr: user.mmr ?? null };
}

type DirtyMap = Partial<Readonly<FieldNamesMarkedBoolean<EditUserInput>>>;

export function pickDirty(
  data: EditUserInput,
  dirty: DirtyMap,
): Partial<EditUserInput> {
  const out: Partial<EditUserInput> = {};
  for (const key of Object.keys(dirty) as (keyof EditUserInput)[]) {
    const flag = dirty[key];
    if (!flag) continue;
    if (key === 'positions' && typeof flag === 'object' && flag !== null) {
      const positions = data.positions;
      const nested: Partial<EditUserInput['positions']> = {};
      for (const slot of Object.keys(flag) as (keyof typeof positions)[]) {
        if ((flag as Record<string, unknown>)[slot]) {
          nested[slot] = positions[slot];
        }
      }
      // Skip writing out.positions for an empty nested map (e.g. flag was {} with no
      // truthy slots) — otherwise the PATCH body would carry a meaningless
      // {positions: {}} that the backend has to validate.
      if (Object.keys(nested).length > 0) {
        out.positions = nested as EditUserInput['positions'];
      }
    } else {
      (out as Record<string, unknown>)[key] = data[key];
    }
  }
  return out;
}

export async function dispatchPatch(
  user: UserClassType,
  scope: EditUserScope,
  payload: Partial<EditUserInput>,
): Promise<UserType> {
  if (scope.kind === 'org') {
    const orgUserPk: number | undefined = user.orgUserPk;
    const orgId: number | undefined = scope.organization.pk;
    if (!orgId) throw new Error('Org scope requires organization.pk');
    if (!orgUserPk) throw new Error('Org scope requires user.orgUserPk');
    return updateOrgUser(orgId, orgUserPk, payload);
  }
  if (scope.kind === 'league') {
    // FLEXIBLE POINT: today routes through the parent org's OrgUser endpoint.
    // When a league-user PATCH endpoint lands, swap this branch.
    const orgId: number | undefined =
      scope.organization?.pk ?? scope.league.organization?.pk;
    const orgUserPk: number | undefined = user.orgUserPk;
    if (!orgId || !orgUserPk) {
      throw new Error('League scope requires a parent org with an OrgUser link');
    }
    return updateOrgUser(orgId, orgUserPk, payload);
  }
  if (!user.pk) throw new Error('Global scope requires user.pk');
  return user.dbUpdate(payload);
}

export function scopeToContext(
  scope: EditUserScope,
): { orgId?: number } | undefined {
  if (scope.kind === 'org') return { orgId: scope.organization.pk };
  if (scope.kind === 'league')
    return { orgId: scope.organization?.pk ?? scope.league.organization?.pk };
  return undefined;
}

export function useScopedEditPermission(scope: EditUserScope): boolean {
  const orgStaff = useIsOrganizationStaff(
    scope.kind === 'org' ? scope.organization : null,
  );
  const leagueAdmin = useIsLeagueAdmin(
    scope.kind === 'league' ? scope.league : null,
    scope.kind === 'league' ? scope.organization : null,
  );
  const superuser = useIsSuperuser();
  if (scope.kind === 'org') return orgStaff;
  if (scope.kind === 'league') return leagueAdmin;
  return superuser;
}

