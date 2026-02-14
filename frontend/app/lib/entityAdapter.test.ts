import { describe, expect, it } from 'vitest';
import { z } from 'zod';
import { createEntityAdapter } from './entityAdapter';

const TestSchema = z.object({
  pk: z.number(),
  name: z.string(),
  discordId: z.string().nullable().optional(),
});

type TestEntity = z.infer<typeof TestSchema> & { pk: number };

const adapter = createEntityAdapter<TestEntity>({
  schema: TestSchema,
  indexes: [{ name: 'byDiscordId', key: 'discordId' }],
});

describe('createEntityAdapter', () => {
  it('getInitialState returns empty state with index maps', () => {
    const state = adapter.getInitialState();
    expect(state.entities).toEqual({});
    expect(state.indexes.byDiscordId).toEqual({});
  });

  it('upsertOne adds entity and indexes', () => {
    const state = adapter.upsertOne(adapter.getInitialState(), {
      pk: 1,
      name: 'Alice',
      discordId: 'abc123',
    });
    expect(state.entities[1]).toEqual({
      pk: 1,
      name: 'Alice',
      discordId: 'abc123',
    });
    expect(state.indexes.byDiscordId['abc123']).toBe(1);
  });

  it('upsertOne returns same state when nothing changed', () => {
    const entity = { pk: 1, name: 'Alice', discordId: 'abc123' };
    const state1 = adapter.upsertOne(adapter.getInitialState(), entity);
    const state2 = adapter.upsertOne(state1, { ...entity });
    expect(state2).toBe(state1); // Same reference
  });

  it('upsertMany preserves references for unchanged entities', () => {
    const entities = [
      { pk: 1, name: 'Alice', discordId: 'a' },
      { pk: 2, name: 'Bob', discordId: 'b' },
    ];
    const state1 = adapter.upsertMany(adapter.getInitialState(), entities);
    const state2 = adapter.upsertMany(state1, [...entities]);
    expect(state2).toBe(state1); // No-op returns same state
    expect(state2.entities[1]).toBe(state1.entities[1]);
  });

  it('upsertMany only replaces changed entities', () => {
    const state1 = adapter.upsertMany(adapter.getInitialState(), [
      { pk: 1, name: 'Alice', discordId: 'a' },
      { pk: 2, name: 'Bob', discordId: 'b' },
    ]);
    const state2 = adapter.upsertMany(state1, [
      { pk: 1, name: 'Alice', discordId: 'a' }, // unchanged
      { pk: 2, name: 'Robert', discordId: 'b' }, // changed
    ]);
    expect(state2).not.toBe(state1);
    expect(state2.entities[1]).toBe(state1.entities[1]); // unchanged ref
    expect(state2.entities[2]).not.toBe(state1.entities[2]); // new ref
  });

  it('upsertMany does not eagerly allocate when nothing changes', () => {
    const state1 = adapter.upsertMany(adapter.getInitialState(), [
      { pk: 1, name: 'Alice', discordId: 'a' },
    ]);
    const state2 = adapter.upsertMany(state1, [
      { pk: 1, name: 'Alice', discordId: 'a' },
    ]);
    expect(state2).toBe(state1);
    expect(state2.entities).toBe(state1.entities); // exact same object
  });

  it('removeOne removes entity and cleans indexes', () => {
    const state1 = adapter.upsertOne(adapter.getInitialState(), {
      pk: 1,
      name: 'Alice',
      discordId: 'abc123',
    });
    const state2 = adapter.removeOne(state1, 1);
    expect(state2.entities[1]).toBeUndefined();
    expect(state2.indexes.byDiscordId['abc123']).toBeUndefined();
  });

  it('removeOne returns same state when pk not found', () => {
    const state = adapter.getInitialState();
    expect(adapter.removeOne(state, 999)).toBe(state);
  });

  it('selectByIndex returns entity by secondary index', () => {
    const state = adapter.upsertOne(adapter.getInitialState(), {
      pk: 1,
      name: 'Alice',
      discordId: 'abc123',
    });
    expect(adapter.selectByIndex(state, 'byDiscordId', 'abc123')).toEqual({
      pk: 1,
      name: 'Alice',
      discordId: 'abc123',
    });
  });

  it('null index keys are not indexed', () => {
    const state = adapter.upsertOne(adapter.getInitialState(), {
      pk: 1,
      name: 'Alice',
      discordId: null,
    });
    expect(Object.keys(state.indexes.byDiscordId)).toHaveLength(0);
  });

  it('index updates when indexed field changes', () => {
    const state1 = adapter.upsertOne(adapter.getInitialState(), {
      pk: 1,
      name: 'Alice',
      discordId: 'old',
    });
    const state2 = adapter.upsertOne(state1, {
      pk: 1,
      name: 'Alice',
      discordId: 'new',
    });
    expect(state2.indexes.byDiscordId['old']).toBeUndefined();
    expect(state2.indexes.byDiscordId['new']).toBe(1);
  });

  it('selectAll returns all entities', () => {
    const state = adapter.upsertMany(adapter.getInitialState(), [
      { pk: 1, name: 'Alice', discordId: 'a' },
      { pk: 2, name: 'Bob', discordId: 'b' },
    ]);
    expect(adapter.selectAll(state)).toHaveLength(2);
  });

  it('removeMany removes multiple entities', () => {
    const state1 = adapter.upsertMany(adapter.getInitialState(), [
      { pk: 1, name: 'Alice', discordId: 'a' },
      { pk: 2, name: 'Bob', discordId: 'b' },
      { pk: 3, name: 'Charlie', discordId: 'c' },
    ]);
    const state2 = adapter.removeMany(state1, [1, 3]);
    expect(Object.keys(state2.entities)).toEqual(['2']);
    expect(state2.indexes.byDiscordId['a']).toBeUndefined();
    expect(state2.indexes.byDiscordId['c']).toBeUndefined();
    expect(state2.indexes.byDiscordId['b']).toBe(2);
  });
});
