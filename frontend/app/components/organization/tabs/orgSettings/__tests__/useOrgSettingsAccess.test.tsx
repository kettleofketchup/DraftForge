// @vitest-environment jsdom
import { renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { OrganizationType } from '~/components/organization/schemas';
import type { UserType } from '~/components/user/types';
import { useUserStore } from '~/store/userStore';
import {
  useOrgSettingsAccess,
  useSettingsTabRedirect,
} from '../useOrgSettingsAccess';

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

describe('useSettingsTabRedirect', () => {
  type Props = {
    tab: string;
    settled: boolean;
    canOpen: boolean;
  };

  function setup(initial: Props) {
    const setActiveTab = vi.fn();
    const hook = renderHook(
      ({ tab, settled, canOpen }: Props) =>
        useSettingsTabRedirect(tab, setActiveTab, { settled, canOpen }),
      { initialProps: initial },
    );
    return { setActiveTab, ...hook };
  }

  it('waits until settled, then redirects a viewer who cannot view', () => {
    const { setActiveTab, rerender } = setup({
      tab: 'settings',
      settled: false,
      canOpen: false,
    });
    expect(setActiveTab).not.toHaveBeenCalled();
    rerender({ tab: 'settings', settled: true, canOpen: false });
    expect(setActiveTab).toHaveBeenCalledWith('leagues');
  });

  it('keeps the settings tab for a viewer who can view', () => {
    const { setActiveTab, rerender } = setup({
      tab: 'settings',
      settled: false,
      canOpen: false,
    });
    rerender({ tab: 'settings', settled: true, canOpen: true });
    expect(setActiveTab).not.toHaveBeenCalled();
  });

  it('never redirects other tabs', () => {
    const { setActiveTab, rerender } = setup({
      tab: 'events',
      settled: false,
      canOpen: false,
    });
    rerender({ tab: 'events', settled: true, canOpen: false });
    expect(setActiveTab).not.toHaveBeenCalled();
  });
});
