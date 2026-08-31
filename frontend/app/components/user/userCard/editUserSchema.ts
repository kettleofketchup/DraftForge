import { z } from 'zod';
import type { FieldNamesMarkedBoolean } from 'react-hook-form';
import type { LeagueType } from '~/components/league/schemas';
import type { OrganizationType } from '~/components/organization/schemas';
import type { UserClassType, UserType } from '~/components/user/types';
import { isUserEntry, type UserEntry } from '~/store/userCacheTypes';
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
  | { kind: 'league'; league: LeagueType; organization?: OrganizationType; orgId?: number }
  | { kind: 'global' };

export type EditableField = keyof EditUserInput;

/**
 * The OrgUser id (orgUserPk) for this user in the given context, or undefined.
 * Flat field first (hydrated tournament users + the errors card's toUserType
 * both carry it); entity-scoped maps as fallback (org/league Users tabs). Keys
 * on id existence, never MMR truthiness, so MMR-0/null-but-linked players still
 * get scope-aware editing.
 */
export function resolveOrgUserLink(
  user: { orgUserPk?: number | null } | UserEntry,
  ctx: { organizationId?: number; leagueId?: number },
): number | undefined {
  const flat = (user as { orgUserPk?: number | null }).orgUserPk;
  if (flat != null) return flat;
  // Narrow via a separate variable: calling isUserEntry(user) directly fails
  // typecheck because the {orgUserPk} union member isn't assignable to
  // UserType (which requires `username`). The cast-to-a-local lets the guard
  // narrow `maybeEntry` so `.orgData`/`.leagueData` resolve.
  const maybeEntry = user as UserType | UserEntry;
  if (isUserEntry(maybeEntry)) {
    const id =
      (ctx.organizationId ? maybeEntry.orgData[ctx.organizationId]?.id : undefined) ??
      (ctx.leagueId ? maybeEntry.leagueData[ctx.leagueId]?.id : undefined);
    if (id != null) return id;
  }
  return undefined;
}

/**
 * Shared edit-scope resolver for the player card AND the incomplete-profiles
 * card. No OrgUser link -> global (nickname/positions only). With a link,
 * league -> org -> global, league scope carrying a DETERMINISTIC orgId from
 * tournament context so the PATCH never depends on currentOrg/
 * currentLeague.organization load timing.
 */
export function resolveEditScope(
  user: { orgUserPk?: number | null } | UserEntry,
  ctx: {
    organizationId?: number;
    leagueId?: number;
    currentOrg: OrganizationType | null;
    currentLeague: LeagueType | null;
  },
): EditUserScope {
  if (resolveOrgUserLink(user, ctx) == null) return { kind: 'global' };
  if (ctx.leagueId && ctx.currentLeague?.pk === ctx.leagueId) {
    return { kind: 'league', league: ctx.currentLeague, orgId: ctx.organizationId };
  }
  if (ctx.currentOrg) return { kind: 'org', organization: ctx.currentOrg };
  return { kind: 'global' };
}

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
      scope.orgId ?? scope.organization?.pk ?? scope.league.organization?.pk;
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
    return { orgId: scope.orgId ?? scope.organization?.pk ?? scope.league.organization?.pk };
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

