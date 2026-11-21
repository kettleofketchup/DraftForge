import type { FieldNamesMarkedBoolean } from 'react-hook-form';
import { z } from 'zod';
import { updateOrgUser } from '~/components/api/api';
import {
  DEFAULT_GAME_TYPE,
  DEFAULT_MMR_BOUNDS,
  GAME_MMR_BOUNDS,
  GAME_TYPE,
  GAME_TYPES,
  isGameType,
  toGameType,
  type GameTypeValue,
} from '~/components/game/constants';
import { parseGameMmrs } from '~/components/game/gameMmrs';
import type { LeagueType } from '~/components/league/schemas';
import type { OrganizationType } from '~/components/organization/schemas';
import type { UserClassType, UserType } from '~/components/user/types';
import {
  useIsLeagueAdmin,
  useIsOrganizationStaff,
  useIsSuperuser,
} from '~/hooks/usePermissions';
import { selectOrgMmr } from '~/store/selectOrgMmr';
import { selectPositions } from '~/store/selectPositions';
import { useUserCacheStore } from '~/store/userCacheStore';
import { isUserEntry, type UserEntry } from '~/store/userCacheTypes';

// Dota positions use a 0-5 self-rating scale: 0=hidden, 1=favorite, 5=avoid.
const PositionFieldSchema = z.coerce.number().int().min(0).max(5);

function mmrField(g: GameTypeValue) {
  const [lo, hi] = GAME_MMR_BOUNDS[g] ?? DEFAULT_MMR_BOUNDS;
  return z.coerce.number().int().min(lo).max(hi).nullable().optional();
}

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
  game_mmrs: z
    .object(Object.fromEntries(GAME_TYPES.map((g) => [String(g), mmrField(g)])))
    .optional(),
});

export type EditUserInput = Omit<
  z.infer<typeof EditUserSchema>,
  'game_mmrs'
> & {
  game_mmrs?: Record<string, number | null | undefined>;
};

// gameType: the context game (tournament/event); unset = every game.
export type EditUserScope =
  | { kind: 'org'; organization: OrganizationType; gameType?: GameTypeValue }
  | {
      kind: 'league';
      league: LeagueType;
      organization?: OrganizationType;
      orgId?: number;
      gameType?: GameTypeValue;
    }
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
      (ctx.organizationId
        ? maybeEntry.orgData[ctx.organizationId]?.id
        : undefined) ??
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
 * currentLeague.organization load timing. `organizationId`/`leagueId` must be
 * the entity's authoritative ids, never derived from currentOrg/currentLeague.
 */
export function resolveEditScope(
  user: { orgUserPk?: number | null } | UserEntry,
  ctx: {
    organizationId?: number;
    leagueId?: number;
    currentOrg: OrganizationType | null;
    currentLeague: LeagueType | null;
    gameType?: GameTypeValue;
  },
): EditUserScope {
  if (resolveOrgUserLink(user, ctx) == null) return { kind: 'global' };
  const game = ctx.gameType != null ? { gameType: ctx.gameType } : {};
  if (ctx.leagueId && ctx.currentLeague?.pk === ctx.leagueId) {
    return {
      kind: 'league',
      league: ctx.currentLeague,
      orgId: ctx.organizationId,
      ...game,
    };
  }
  if (ctx.currentOrg && ctx.currentOrg.pk === ctx.organizationId) {
    return { kind: 'org', organization: ctx.currentOrg, ...game };
  }
  return { kind: 'global' };
}

/** The org MMR games the edit form shows for this scope. */
export function editableGames(scope: EditUserScope): GameTypeValue[] {
  if (scope.kind === 'global') return [];
  if (scope.gameType != null) return [scope.gameType];
  return scope.kind === 'org' ? [...GAME_TYPES] : [DEFAULT_GAME_TYPE];
}

function defaultMmr(
  user: UserClassType,
  scope: EditUserScope,
  game: GameTypeValue,
): number | null {
  if (scope.kind !== 'global' && scope.gameType != null) {
    return user.mmr ?? null;
  }
  const orgId = scopeToContext(scope)?.orgId;
  const entry =
    user.pk != null
      ? useUserCacheStore.getState().entities[user.pk]
      : undefined;
  return (
    selectOrgMmr(entry, orgId, game) ??
    parseGameMmrs(user.game_mmrs)[game] ??
    (toGameType(user.mmr_game_type) === game ? user.mmr : undefined) ??
    null
  );
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
  const base: Omit<EditUserInput, 'game_mmrs'> = {
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
  const games = editableGames(scope);
  if (games.length === 0) return base;
  return {
    ...base,
    game_mmrs: Object.fromEntries(
      games.map((g) => [String(g), defaultMmr(user, scope, g)]),
    ),
  };
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
    } else if (
      key === 'game_mmrs' &&
      typeof flag === 'object' &&
      flag !== null
    ) {
      const games: Record<string, number | null | undefined> = {};
      for (const [g, isDirty] of Object.entries(flag)) {
        if (isDirty) games[g] = data.game_mmrs?.[g] ?? null;
      }
      if (Object.keys(games).length > 0) out.game_mmrs = games;
    } else {
      (out as Record<string, unknown>)[key] = data[key];
    }
  }
  return out;
}

/**
 * Mirror the server response back onto the passed instance. The global branch
 * gets this for free from User.dbUpdate's in-place Object.assign; the org and
 * league branches go through a bare axios call that mutates nothing locally.
 * Without the parity, buildDefaults re-seeds the pre-edit values on reopen and
 * RHF reports the form clean, so a second edit sends no request at all.
 *
 * OrgUserSerializer maps pk -> user.pk, so user.pk survives the merge.
 */
function applyLocal(user: UserClassType, updated: UserType): UserType {
  Object.assign(user, updated);
  return updated;
}

type OrgUserPatch = Omit<Partial<EditUserInput>, 'game_mmrs'> & {
  game_mmrs?: Partial<Record<GameTypeValue, number | null>>;
};

function toOrgUserPatch(payload: Partial<EditUserInput>): OrgUserPatch {
  const { game_mmrs, ...rest } = payload;
  if (!game_mmrs) return rest;
  const games: Partial<Record<GameTypeValue, number | null>> = {};
  for (const [key, value] of Object.entries(game_mmrs)) {
    const g = Number(key);
    if (isGameType(g)) games[g] = value ?? null;
  }
  return { ...rest, game_mmrs: games };
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
    return applyLocal(
      user,
      await updateOrgUser(
        orgId,
        orgUserPk,
        toOrgUserPatch(payload),
        scope.gameType ?? GAME_TYPE.DOTA2,
      ),
    );
  }
  if (scope.kind === 'league') {
    // FLEXIBLE POINT: today routes through the parent org's OrgUser endpoint.
    // When a league-user PATCH endpoint lands, swap this branch.
    const orgId: number | undefined =
      scope.orgId ?? scope.organization?.pk ?? scope.league.organization?.pk;
    const orgUserPk: number | undefined = user.orgUserPk;
    if (!orgId || !orgUserPk) {
      throw new Error(
        'League scope requires a parent org with an OrgUser link',
      );
    }
    return applyLocal(
      user,
      await updateOrgUser(
        orgId,
        orgUserPk,
        toOrgUserPatch(payload),
        scope.gameType ?? GAME_TYPE.DOTA2,
      ),
    );
  }
  if (!user.pk) throw new Error('Global scope requires user.pk');
  const { game_mmrs: _orgOnly, ...globalPayload } = payload;
  return user.dbUpdate(globalPayload);
}

export function scopeToContext(
  scope: EditUserScope,
): { orgId?: number } | undefined {
  if (scope.kind === 'org') return { orgId: scope.organization.pk };
  if (scope.kind === 'league')
    return {
      orgId:
        scope.orgId ?? scope.organization?.pk ?? scope.league.organization?.pk,
    };
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
