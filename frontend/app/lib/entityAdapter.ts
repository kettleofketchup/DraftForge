import type { ZodObject, ZodRawShape } from 'zod';

export interface IndexConfig {
  name: string;
  key: string;
}

export interface EntityState<T> {
  entities: Record<number, T>;
  indexes: Record<string, Record<string | number, number>>;
}

export interface EntityAdapterConfig<T> {
  schema: ZodObject<ZodRawShape>;
  indexes?: IndexConfig[];
  hasChanged?: (existing: T, incoming: T) => boolean;
}

export interface EntityAdapter<T extends { pk: number }> {
  getInitialState(): EntityState<T>;
  upsertMany(state: EntityState<T>, entities: T[]): EntityState<T>;
  upsertOne(state: EntityState<T>, entity: T): EntityState<T>;
  removeOne(state: EntityState<T>, pk: number): EntityState<T>;
  removeMany(state: EntityState<T>, pks: number[]): EntityState<T>;
  selectById(state: EntityState<T>, pk: number): T | undefined;
  selectAll(state: EntityState<T>): T[];
  selectByIndex(
    state: EntityState<T>,
    indexName: string,
    key: string | number,
  ): T | undefined;
  /** Exposed for direct index management in custom upsert logic. */
  updateIndexesForEntity(
    indexes: Record<string, Record<string | number, number>>,
    entity: T,
    oldEntity?: T,
  ): Record<string, Record<string | number, number>>;
}

export function createEntityAdapter<T extends { pk: number }>(
  config: EntityAdapterConfig<T>,
): EntityAdapter<T> {
  const coreKeys = Object.keys(config.schema.shape) as (keyof T)[];
  const indexConfigs = config.indexes ?? [];

  function defaultHasChanged(existing: T, incoming: T): boolean {
    return coreKeys.some((k) => existing[k] !== incoming[k]);
  }

  const hasChanged = config.hasChanged ?? defaultHasChanged;

  function updateIndexesForEntity(
    indexes: Record<string, Record<string | number, number>>,
    entity: T,
    oldEntity?: T,
  ): Record<string, Record<string | number, number>> {
    let changed = false;
    const newIndexes = { ...indexes };

    for (const idx of indexConfigs) {
      const newVal = (entity as Record<string, unknown>)[idx.key];
      const oldVal = oldEntity
        ? (oldEntity as Record<string, unknown>)[idx.key]
        : undefined;

      if (newVal !== oldVal) {
        changed = true;
        newIndexes[idx.name] = { ...newIndexes[idx.name] };
        // Remove old index entry
        if (oldVal != null) {
          delete newIndexes[idx.name][oldVal as string | number];
        }
        // Add new index entry
        if (newVal != null) {
          newIndexes[idx.name][newVal as string | number] = entity.pk;
        }
      }
    }

    return changed ? newIndexes : indexes;
  }

  return {
    getInitialState(): EntityState<T> {
      const indexes: Record<string, Record<string | number, number>> = {};
      for (const idx of indexConfigs) {
        indexes[idx.name] = {};
      }
      return { entities: {}, indexes };
    },

    upsertOne(state: EntityState<T>, entity: T): EntityState<T> {
      const existing = state.entities[entity.pk];
      if (existing && !hasChanged(existing, entity)) {
        return state;
      }
      const newEntities = { ...state.entities, [entity.pk]: entity };
      const newIndexes = updateIndexesForEntity(
        state.indexes,
        entity,
        existing,
      );
      return { entities: newEntities, indexes: newIndexes };
    },

    // Lazy spread: only allocates when first change is detected
    upsertMany(state: EntityState<T>, entities: T[]): EntityState<T> {
      let newEntities: Record<number, T> | null = null;
      let newIndexes = state.indexes;

      for (const entity of entities) {
        const existing = (newEntities ?? state.entities)[entity.pk];
        if (existing && !hasChanged(existing, entity)) {
          continue;
        }
        if (!newEntities) newEntities = { ...state.entities };
        newEntities[entity.pk] = entity;
        newIndexes = updateIndexesForEntity(newIndexes, entity, existing);
      }

      if (!newEntities) return state;
      return { entities: newEntities, indexes: newIndexes };
    },

    removeOne(state: EntityState<T>, pk: number): EntityState<T> {
      const entity = state.entities[pk];
      if (!entity) return state;

      const newEntities = { ...state.entities };
      delete newEntities[pk];

      const newIndexes = { ...state.indexes };
      for (const idx of indexConfigs) {
        const val = (entity as Record<string, unknown>)[idx.key];
        if (val != null) {
          newIndexes[idx.name] = { ...newIndexes[idx.name] };
          delete newIndexes[idx.name][val as string | number];
        }
      }

      return { entities: newEntities, indexes: newIndexes };
    },

    removeMany(state: EntityState<T>, pks: number[]): EntityState<T> {
      let result = state;
      for (const pk of pks) {
        result = this.removeOne(result, pk);
      }
      return result;
    },

    selectById(state: EntityState<T>, pk: number): T | undefined {
      return state.entities[pk];
    },

    selectAll(state: EntityState<T>): T[] {
      return Object.values(state.entities);
    },

    selectByIndex(
      state: EntityState<T>,
      indexName: string,
      key: string | number,
    ): T | undefined {
      const pk = state.indexes[indexName]?.[key];
      return pk != null ? state.entities[pk] : undefined;
    },

    updateIndexesForEntity,
  };
}
