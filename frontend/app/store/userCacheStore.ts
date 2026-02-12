import { create } from 'zustand';
import { devtools } from 'zustand/middleware';

import { CoreUserSchema } from '~/components/user/schemas';
import type { CoreUserType } from '~/components/user/schemas';
import type { UserType } from '~/components/user/types';
import { createEntityAdapter, type EntityState } from '~/lib/entityAdapter';
import { getLogger } from '~/lib/logger';

import type {
  LeagueUserData,
  OrgUserData,
  UpsertContext,
  UserEntry,
} from './userCacheTypes';

const log = getLogger('UserCache');

// Core keys derived from schema — single source of truth
const coreKeys = Object.keys(CoreUserSchema.shape) as (keyof CoreUserType)[];

function pick<T extends Record<string, unknown>>(
  obj: T,
  keys: string[],
): Partial<T> {
  const result: Record<string, unknown> = {};
  for (const key of keys) {
    if (key in obj) {
      result[key] = obj[key];
    }
  }
  return result as Partial<T>;
}

function hasCoreChanged(existing: UserEntry, incoming: UserEntry): boolean {
  return coreKeys.some(
    (k) => existing[k as keyof UserEntry] !== incoming[k as keyof UserEntry],
  );
}

function hasScopedChanged(
  existing: UserEntry,
  incoming: UserEntry,
  context?: UpsertContext,
): boolean {
  if (hasCoreChanged(existing, incoming)) return true;

  if (context?.orgId) {
    const a = existing.orgData[context.orgId];
    const b = incoming.orgData[context.orgId];
    if (a?.mmr !== b?.mmr || a?.id !== b?.id) return true;
  }
  if (context?.leagueId) {
    const a = existing.leagueData[context.leagueId];
    const b = incoming.leagueData[context.leagueId];
    if (a?.mmr !== b?.mmr || a?.id !== b?.id) return true;
  }

  return false;
}

export const userAdapter = createEntityAdapter<UserEntry>({
  schema: CoreUserSchema,
  indexes: [
    { name: 'byDiscordId', key: 'discordId' },
    { name: 'bySteamId', key: 'steamid' },
  ],
});

function toUserEntry(
  raw: UserType & { pk: number },
  context?: UpsertContext,
  existing?: UserEntry,
): UserEntry {
  const now = Date.now();

  // Extract core fields from raw user using schema keys
  const coreFields = pick(raw, coreKeys as string[]);

  // Only create new scoped data objects when context provides data.
  // Reuse existing references when no update is needed to avoid
  // unnecessary re-renders.
  let orgData = existing?.orgData ?? {};
  let leagueData = existing?.leagueData ?? {};

  if (context?.orgId && raw.mmr != null && raw.id != null) {
    orgData = {
      ...orgData,
      [context.orgId]: {
        id: raw.id,
        mmr: raw.mmr,
        _fetchedAt: now,
      },
    };
  }

  if (context?.leagueId && raw.league_mmr != null && raw.id != null) {
    leagueData = {
      ...leagueData,
      [context.leagueId]: {
        id: raw.id,
        mmr: raw.league_mmr,
        _fetchedAt: now,
      },
    };
  }

  return {
    ...(existing ?? {}),
    ...coreFields,
    pk: raw.pk,
    orgData,
    leagueData,
    _fetchedAt: now,
  } as UserEntry;
}

interface UserCacheState extends EntityState<UserEntry> {
  staleAfterMs: number;

  // Write operations
  upsert(
    incoming: UserType | UserType[],
    context?: UpsertContext,
  ): void;
  remove(pk: number): void;

  // Read operations
  getById(pk: number): UserEntry | undefined;
  getByDiscordId(discordId: string): UserEntry | undefined;
  getBySteamId(steamid: number): UserEntry | undefined;

  // Staleness
  isStale(pk: number, context?: UpsertContext): boolean;

  // Lifecycle
  reset(): void;
}

export const useUserCacheStore = create<UserCacheState>()(
  devtools(
    (set, get) => ({
      ...userAdapter.getInitialState(),
      staleAfterMs: 5 * 60 * 1000, // 5 minutes

      // CRITICAL: This method bypasses userAdapter.upsertMany() and does
      // its own merge loop. The adapter's hasChanged only checks core keys
      // (from CoreUserSchema.shape) and would silently drop scoped data
      // changes (MMR updates). We use hasScopedChanged instead, and call
      // adapter.updateIndexesForEntity for index management.
      upsert(incoming, context) {
        const rawUsers = Array.isArray(incoming) ? incoming : [incoming];
        // Filter out users with undefined pk (UserType.pk is optional)
        const users = rawUsers.filter(
          (u): u is UserType & { pk: number } => u.pk != null,
        );
        if (users.length === 0) return;

        const state = get();
        let newEntities: Record<number, UserEntry> | null = null;
        let newIndexes = state.indexes;

        for (const raw of users) {
          const existing = (newEntities ?? state.entities)[raw.pk];
          const entry = toUserEntry(raw, context, existing);

          if (existing && !hasScopedChanged(existing, entry, context)) {
            continue;
          }

          if (!newEntities) newEntities = { ...state.entities };
          newEntities[entry.pk] = entry;
          newIndexes = userAdapter.updateIndexesForEntity(
            newIndexes,
            entry,
            existing,
          );
        }

        if (!newEntities) {
          log.debug(
            `Skipping upsert — ${users.length} users unchanged`,
          );
          return;
        }

        set(
          { entities: newEntities, indexes: newIndexes },
          undefined,
          'upsert',
        );
        log.debug(`Upserted ${users.length} users`, context);
      },

      remove(pk) {
        const state = get();
        const newState = userAdapter.removeOne(
          { entities: state.entities, indexes: state.indexes },
          pk,
        );
        if (newState.entities === state.entities) return;
        set(
          { entities: newState.entities, indexes: newState.indexes },
          undefined,
          'remove',
        );
      },

      getById(pk) {
        return get().entities[pk];
      },

      getByDiscordId(discordId) {
        return userAdapter.selectByIndex(
          get(),
          'byDiscordId',
          discordId,
        );
      },

      getBySteamId(steamid) {
        return userAdapter.selectByIndex(
          get(),
          'bySteamId',
          steamid,
        );
      },

      isStale(pk, context) {
        const entry = get().entities[pk];
        if (!entry) return true;

        const now = Date.now();
        const staleMs = get().staleAfterMs;

        // Check core staleness
        if (now - entry._fetchedAt > staleMs) return true;

        // Check scoped staleness
        if (context?.orgId) {
          const orgEntry = entry.orgData[context.orgId];
          if (!orgEntry || now - orgEntry._fetchedAt > staleMs) return true;
        }
        if (context?.leagueId) {
          const leagueEntry = entry.leagueData[context.leagueId];
          if (!leagueEntry || now - leagueEntry._fetchedAt > staleMs)
            return true;
        }

        return false;
      },

      reset() {
        set(
          { ...userAdapter.getInitialState() },
          undefined,
          'reset',
        );
        log.debug('Cache cleared');
      },
    }),
    { name: 'UserCache', enabled: process.env.NODE_ENV === 'development' },
  ),
);
