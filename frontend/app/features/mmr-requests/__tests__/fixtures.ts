import type { MmrChangeRequest, UserMmrSummary } from '../schemas';

export function mmrRequest(
  overrides: Partial<MmrChangeRequest> = {},
): MmrChangeRequest {
  return {
    id: 77,
    target: 'org',
    game_type: 1,
    status: 'pending',
    source: 'member',
    requested_mmr: 4800,
    approved_mmr: null,
    previous_mmr: 4200,
    previous_verified: false,
    note: 'New season',
    rejection_reason: '',
    reviewed_at: null,
    reviewed_by_username: null,
    created_at: '2026-11-21T10:00:00Z',
    subject: {
      pk: 42,
      username: 'member',
      nickname: null,
      avatarUrl: null,
    },
    requester_username: 'member',
    organization: { pk: 3, name: 'Org X' },
    league: null,
    current_mmr: 4200,
    current_verified: false,
    has_screenshot: true,
    screenshot_url: '/api/mmr-requests/77/screenshot/',
    can_review: true,
    ...overrides,
  };
}

export function mmrSummary(): UserMmrSummary {
  return {
    user_pk: 42,
    orgs: [
      {
        organization: { pk: 3, name: 'Org X', logo: null },
        org_user_pk: 117,
        game_mmrs: [
          {
            game_type: 1,
            mmr: 4750,
            verified: true,
            verified_at: '2026-11-22T10:00:00Z',
            verified_by: { pk: 9, username: 'staffy' },
            legacy_verified: false,
            pending_request: null,
            last_decision: null,
          },
        ],
      },
    ],
    leagues: [
      {
        league: { pk: 5, name: 'Season 4' },
        organization_pk: 3,
        league_user_pk: 300,
        mmr: 4900,
        verified: false,
        verified_at: null,
        verified_by: null,
        pending_request: {
          id: 77,
          requested_mmr: 5100,
          created_at: '2026-11-21T10:00:00Z',
        },
        last_decision: {
          id: 70,
          status: 'rejected',
          decided_mmr: null,
          rejection_reason: 'Blurry',
          reviewed_at: '2026-11-18T10:00:00Z',
        },
      },
    ],
  };
}
