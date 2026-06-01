import { describe, expect, it, beforeEach } from 'vitest';

import { useUserProfileStore } from './userProfileStore';
import type { UserProfileEntry } from './userProfileTypes';

function entry(pk: number, nickname: string | null = 'X'): UserProfileEntry {
  return {
    pk,
    base: { nickname, avatar: null },
    gameUser: {},
    orgProfiles: {},
    _fetchedAt: Date.now(),
  };
}

describe('userProfileStore', () => {
  beforeEach(() => {
    useUserProfileStore.getState().reset();
  });

  it('starts empty', () => {
    expect(useUserProfileStore.getState().entities).toEqual({});
  });

  it('upserts a profile entry', () => {
    useUserProfileStore.getState().upsert(entry(1, 'Alice'));
    expect(useUserProfileStore.getState().entities[1]?.base.nickname).toBe('Alice');
  });

  it('selectBase returns the base profile', () => {
    useUserProfileStore.getState().upsert(entry(2, 'Bob'));
    const base = useUserProfileStore.getState().selectBase(2);
    expect(base).toEqual({ nickname: 'Bob', avatar: null });
  });

  it('upsert returns same identity when nothing changed', () => {
    const e = entry(3, 'Carol');
    useUserProfileStore.getState().upsert(e);
    const first = useUserProfileStore.getState().entities[3];
    useUserProfileStore.getState().upsert({ ...e });   // same content
    const second = useUserProfileStore.getState().entities[3];
    expect(second).toBe(first);   // referential equality preserved
  });

  it('reset clears all entries', () => {
    useUserProfileStore.getState().upsert(entry(4, 'D'));
    useUserProfileStore.getState().reset();
    expect(useUserProfileStore.getState().entities).toEqual({});
  });
});
