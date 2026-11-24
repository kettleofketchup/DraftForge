// @vitest-environment jsdom
import { renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import type { OrganizationType } from '~/components/organization/schemas';
import type { UserType } from '~/components/user/types';
import { useUserStore } from '~/store/userStore';
import { useOrgSettingsAccess } from '../useOrgSettingsAccess';

const VIEWER = 5;

function setViewer(pk: number | null, isStaff = false) {
  useUserStore.setState({
    currentUser: (pk == null
      ? {}
      : { pk, username: `u${pk}`, is_staff: isStaff }) as UserType,
  });
}

function org(
  overrides: Partial<OrganizationType> = {},
  viewerPk: number | null | undefined = VIEWER,
): OrganizationType {
  return {
    pk: 7,
    name: 'Org',
    owner_id: 1,
    admin_ids: [],
    staff_ids: [],
    members_viewer_pk: viewerPk,
    ...overrides,
  } as OrganizationType;
}

function access(o: OrganizationType | undefined) {
  return renderHook(() => useOrgSettingsAccess(o)).result.current;
}

describe('useOrgSettingsAccess', () => {
  beforeEach(() => setViewer(VIEWER));

  it('denies org staff', () => {
    expect(access(org({ staff_ids: [VIEWER] }))).toEqual({
      settled: true,
      canOpen: false,
      visibleSectionIds: [],
    });
  });

  it('denies a plain member', () => {
    const result = access(org());
    expect(result.settled).toBe(true);
    expect(result.canOpen).toBe(false);
  });

  it('allows the owner', () => {
    expect(access(org({ owner_id: VIEWER }))).toEqual({
      settled: true,
      canOpen: true,
      visibleSectionIds: ['staff-placement'],
    });
  });

  it('shows the conduct section only with can_manage_conduct', () => {
    expect(access(org({ owner_id: VIEWER, can_manage_conduct: true }))).toEqual(
      {
        settled: true,
        canOpen: true,
        visibleSectionIds: ['staff-placement', 'conduct'],
      },
    );
    expect(
      access(org({ owner_id: VIEWER, can_manage_conduct: false }))
        .visibleSectionIds,
    ).toEqual(['staff-placement']);
  });

  it('shows the leadership section only with leadership manage access', () => {
    const track = (canManage: boolean) => ({
      key: 'leadership',
      label: 'Leadership',
      metrics: [{ key: 'points', label: 'Points' }],
      can_view_rows: true,
      can_view_own: true,
      board_open: true,
      can_manage: canManage,
      can_moderate: canManage,
    });
    expect(
      access(
        org({
          owner_id: VIEWER,
          standing_tracks: [track(true)],
        } as Partial<OrganizationType>),
      ).visibleSectionIds,
    ).toEqual(['staff-placement', 'leadership']);
    expect(
      access(
        org({
          owner_id: VIEWER,
          standing_tracks: [track(false)],
        } as Partial<OrganizationType>),
      ).visibleSectionIds,
    ).toEqual(['staff-placement']);
  });

  it('shows the api access section only while mmr_sync is on', () => {
    expect(
      access(org({ owner_id: VIEWER, features: ['mmr_sync'] }))
        .visibleSectionIds,
    ).toEqual(['staff-placement', 'api-access']);
    expect(
      access(org({ owner_id: VIEWER, features: [] })).visibleSectionIds,
    ).toEqual(['staff-placement']);
  });

  it('shows the api access section to a site admin while locked', () => {
    setViewer(VIEWER, true);
    expect(access(org({ features: [] })).visibleSectionIds).toContain(
      'api-access',
    );
  });

  it('allows an org admin', () => {
    expect(access(org({ admin_ids: [VIEWER] })).canOpen).toBe(true);
  });

  it('allows a site admin', () => {
    setViewer(VIEWER, true);
    expect(access(org()).canOpen).toBe(true);
  });

  it('is not settled while the org is loading', () => {
    expect(access(undefined)).toEqual({
      settled: false,
      canOpen: false,
      visibleSectionIds: [],
    });
  });

  it('is not settled while members_viewer_pk is undefined', () => {
    const result = access(
      org({ admin_ids: [VIEWER], members_viewer_pk: undefined }),
    );
    expect(result.settled).toBe(false);
    expect(result.canOpen).toBe(false);
  });

  it('is not settled while the payload viewer differs', () => {
    const result = access(org({ admin_ids: [VIEWER] }, 9));
    expect(result.settled).toBe(false);
    expect(result.canOpen).toBe(false);
  });

  it('is not settled before the current user resolves', () => {
    setViewer(null);
    const result = access(org({ admin_ids: [VIEWER] }));
    expect(result.settled).toBe(false);
    expect(result.canOpen).toBe(false);
  });
});
