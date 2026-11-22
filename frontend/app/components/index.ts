import {
  DraftRoundSchema,
  DraftSchema,
  TeamDraftRoundSchema,
  TeamDraftSchema,
} from './teamdraft/schemas';
import type {
  DraftRoundType,
  DraftType,
  TeamDraftRoundType,
  TeamDraftType,
} from './teamdraft/types';

// Primary exports with explicit TeamDraft naming
export { TeamDraftRoundSchema, TeamDraftSchema };
export type { TeamDraftRoundType, TeamDraftType };

// Backwards compatibility aliases
export { DraftRoundSchema, DraftSchema };
export type { DraftRoundType, DraftType };
