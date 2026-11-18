import { beforeEach, describe, expect, it } from 'vitest';

import { useDisplayOrgStore } from '../displayOrgStore';

const state = () => useDisplayOrgStore.getState();

describe('displayOrgStore', () => {
  beforeEach(() => useDisplayOrgStore.setState({ stack: [], orgId: null }));

  it('starts with no org', () => {
    expect(state().orgId).toBeNull();
  });

  it('nests and unwinds', () => {
    const outer = state().push(1);
    const inner = state().push(2);
    expect(state().orgId).toBe(2);
    state().pop(inner);
    expect(state().orgId).toBe(1);
    state().pop(outer);
    expect(state().orgId).toBeNull();
  });

  it('a null frame hides the outer org', () => {
    state().push(1);
    const none = state().push(null);
    expect(state().orgId).toBeNull();
    state().pop(none);
    expect(state().orgId).toBe(1);
  });

  it('pops out of order without disturbing the top', () => {
    const outer = state().push(1);
    state().push(2);
    state().pop(outer);
    expect(state().orgId).toBe(2);
    expect(state().stack).toHaveLength(1);
  });

  it('ignores an unknown token', () => {
    state().push(1);
    const before = state().stack;
    state().pop(999);
    expect(state().stack).toBe(before);
  });
});
