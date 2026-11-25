import type {
  CandidateRow,
  CandidatesResponse,
  ContactSync,
  ExternalContact,
} from '../schemas';

export function candidateRow(
  overrides: Partial<CandidateRow> = {},
): CandidateRow {
  return {
    user_pk: 42,
    username: 'ana',
    nickname: null,
    discordUsername: 'ana_dc',
    discordId: '1234',
    avatarUrl: null,
    mmr: null,
    recent_count: 2,
    last_messaged: null,
    contact_recorded: false,
    external_contact: null,
    earning_send_exists: false,
    signed_up: false,
    ...overrides,
  };
}

export const SFG_CONTACT: ExternalContact = {
  source: 'sfg',
  recorded_at: '2026-11-24T11:30:00Z',
  delivery_verified: false,
  can_undo: false,
};

export const NO_SYNC: ContactSync = {
  configured: false,
  last_receipt_imported_at: null,
  warning: null,
};

export const SYNC_CONFIGURED: ContactSync = {
  configured: true,
  last_receipt_imported_at: '2026-11-24T11:35:00Z',
  warning: 'history_may_be_incomplete',
};

export function candidatesResponse(
  rows: CandidateRow[],
  overrides: Partial<CandidatesResponse> = {},
): CandidatesResponse {
  return {
    source: 'recent',
    n: 3,
    days: 30,
    game_type: 1,
    min_mmr: null,
    max_mmr: null,
    rows,
    contact_sync: NO_SYNC,
    ...overrides,
  };
}
