import { create } from 'zustand';
import { devtools } from 'zustand/middleware';

import type { BaseProfile, UserProfileEntry } from './userProfileTypes';

interface UserProfileState {
  entities: Record<number, UserProfileEntry>;

  upsert: (entry: UserProfileEntry) => void;
  reset: () => void;
  selectBase: (userPk: number) => BaseProfile | undefined;
}

function sameBase(a: BaseProfile, b: BaseProfile): boolean {
  return a.nickname === b.nickname && a.avatar === b.avatar;
}

function sameGameUser(
  a: UserProfileEntry['gameUser'],
  b: UserProfileEntry['gameUser'],
): boolean {
  return a.dota === b.dota && a.deadlock === b.deadlock;
}

function sameOrgProfiles(
  a: UserProfileEntry['orgProfiles'],
  b: UserProfileEntry['orgProfiles'],
): boolean {
  const ka = Object.keys(a);
  const kb = Object.keys(b);
  if (ka.length !== kb.length) return false;
  for (const k of ka) {
    if (a[Number(k)] !== b[Number(k)]) return false;
  }
  return true;
}

/**
 * Custom hasChanged: compare base + gameUser + orgProfiles slots.
 * Default schema-only equality would silently drop nested updates.
 * Mirrors userCacheStore.ts:41-60 (hasScopedChanged).
 */
function hasChanged(existing: UserProfileEntry, incoming: UserProfileEntry): boolean {
  return (
    !sameBase(existing.base, incoming.base) ||
    !sameGameUser(existing.gameUser, incoming.gameUser) ||
    !sameOrgProfiles(existing.orgProfiles, incoming.orgProfiles)
  );
}

export const useUserProfileStore = create<UserProfileState>()(
  devtools(
    (set, get) => ({
      entities: {},

      upsert: (entry) =>
        set(
          (state) => {
            const existing = state.entities[entry.pk];
            if (existing && !hasChanged(existing, entry)) {
              // Identity preserved — no re-render trigger for unchanged content.
              return state;
            }
            return {
              entities: { ...state.entities, [entry.pk]: entry },
            };
          },
          false,
          'userProfile/upsert',
        ),

      reset: () => set({ entities: {} }, false, 'userProfile/reset'),

      selectBase: (userPk) => get().entities[userPk]?.base,
    }),
    { name: 'userProfileStore' },
  ),
);
