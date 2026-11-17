import { beforeEach, describe, expect, it } from 'vitest';

import { useUserProfileStore } from './userProfileStore';
import type { UserProfileEntry } from './userProfileTypes';

function entry(pk: number, avatar: string | null = null): UserProfileEntry {
  return {
    pk,
    base: { avatar },
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
    useUserProfileStore.getState().upsert(entry(1, 'a'));
    expect(useUserProfileStore.getState().entities[1]?.base.avatar).toBe('a');
  });

  it('selectBase returns the base profile', () => {
    useUserProfileStore.getState().upsert(entry(2, 'b'));
    const base = useUserProfileStore.getState().selectBase(2);
    expect(base).toEqual({ avatar: 'b' });
  });

  it('upsert returns same identity when nothing changed', () => {
    const e = entry(3, 'c');
    useUserProfileStore.getState().upsert(e);
    const first = useUserProfileStore.getState().entities[3];
    useUserProfileStore.getState().upsert({ ...e }); // same content
    const second = useUserProfileStore.getState().entities[3];
    expect(second).toBe(first); // referential equality preserved
  });

  it('base equality compares the avatar only', () => {
    const e = entry(5);
    useUserProfileStore.getState().upsert(e);
    const first = useUserProfileStore.getState().entities[5];
    useUserProfileStore.getState().upsert({ ...e, base: { avatar: null } });
    expect(useUserProfileStore.getState().entities[5]).toBe(first);
    useUserProfileStore.getState().upsert({ ...e, base: { avatar: 'h' } });
    expect(useUserProfileStore.getState().entities[5]?.base.avatar).toBe('h');
  });

  it('reset clears all entries', () => {
    useUserProfileStore.getState().upsert(entry(4));
    useUserProfileStore.getState().reset();
    expect(useUserProfileStore.getState().entities).toEqual({});
  });
});
