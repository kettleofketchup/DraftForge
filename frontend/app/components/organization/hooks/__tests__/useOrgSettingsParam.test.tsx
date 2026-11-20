// @vitest-environment jsdom
import { act, renderHook } from '@testing-library/react';
import type { ReactNode } from 'react';
import {
  MemoryRouter,
  useLocation,
  useNavigate,
  useNavigationType,
} from 'react-router';
import { describe, expect, it } from 'vitest';
import { useOrgSettingsParam } from '../useOrgSettingsParam';

type Access = { settled: boolean; canOpen: boolean };

const ADMIN: Access = { settled: true, canOpen: true };

function setup(url: string, initial: Access = ADMIN) {
  const wrapper = ({ children }: { children: ReactNode }) => (
    <MemoryRouter initialEntries={[url]}>{children}</MemoryRouter>
  );
  return renderHook(
    (access: Access) => ({
      param: useOrgSettingsParam(access),
      location: useLocation(),
      navigationType: useNavigationType(),
      navigate: useNavigate(),
    }),
    { wrapper, initialProps: initial },
  );
}

const search = (r: { current: { location: { search: string } } }) =>
  new URLSearchParams(r.current.location.search);

describe('useOrgSettingsParam', () => {
  it('is closed without the settings param', () => {
    const { result } = setup('/organizations/7');
    expect(result.current.param.open).toBe(false);
    expect(result.current.param.section).toBeNull();
  });

  it('treats an empty settings param as open with no section', () => {
    const { result } = setup('/organizations/7?settings=');
    expect(result.current.param.open).toBe(true);
    expect(result.current.param.section).toBeNull();
  });

  it('reads the section from the settings param', () => {
    const { result } = setup('/organizations/7?settings=admins');
    expect(result.current.param.open).toBe(true);
    expect(result.current.param.section).toBe('admins');
  });

  it('openSettings sets an empty settings param', () => {
    const { result } = setup('/organizations/7?tab=events');
    act(() => result.current.param.openSettings());
    expect(search(result).get('settings')).toBe('');
    expect(search(result).get('tab')).toBe('events');
    expect(result.current.param.open).toBe(true);
  });

  it('openSettings with a section opens on that section', () => {
    const { result } = setup('/organizations/7');
    act(() => result.current.param.openSettings('staff-placement'));
    expect(result.current.param.section).toBe('staff-placement');
  });

  it('legacy ?tab=settings&section=staff-placement becomes ?settings=staff-placement', () => {
    const { result } = setup(
      '/organizations/7?tab=settings&section=staff-placement',
    );
    const params = search(result);
    expect(params.get('settings')).toBe('staff-placement');
    expect(params.has('tab')).toBe(false);
    expect(params.has('section')).toBe(false);
    expect(result.current.param.section).toBe('staff-placement');
  });

  it('legacy ?tab=settings without a section opens with an empty param', () => {
    const { result } = setup('/organizations/7?tab=settings');
    expect(search(result).get('settings')).toBe('');
    expect(search(result).has('tab')).toBe(false);
    expect(result.current.param.open).toBe(true);
  });

  it('keeps the param while access is unsettled', () => {
    const { result } = setup('/organizations/7?settings=admins', {
      settled: false,
      canOpen: false,
    });
    expect(search(result).get('settings')).toBe('admins');
  });

  it('removes settings param when settled without access (org staff, not admin)', () => {
    const { result, rerender } = setup('/organizations/7?settings=admins', {
      settled: false,
      canOpen: false,
    });
    rerender({ settled: true, canOpen: false });
    expect(search(result).has('settings')).toBe(false);
    expect(result.current.param.open).toBe(false);
  });

  it('removes a legacy settings link once settled without access', () => {
    const { result } = setup('/organizations/7?tab=settings&section=admins', {
      settled: true,
      canOpen: false,
    });
    const params = search(result);
    expect(params.has('settings')).toBe(false);
    expect(params.has('tab')).toBe(false);
    expect(params.has('section')).toBe(false);
  });

  it('keeps the param for an admin once settled', () => {
    const { result, rerender } = setup('/organizations/7?settings=admins', {
      settled: false,
      canOpen: false,
    });
    rerender(ADMIN);
    expect(search(result).get('settings')).toBe('admins');
  });

  it('close removes the param', () => {
    const { result } = setup('/organizations/7?tab=events&settings=admins');
    act(() => result.current.param.close());
    expect(search(result).has('settings')).toBe(false);
    expect(search(result).get('tab')).toBe('events');
    expect(result.current.param.open).toBe(false);
  });

  it('setSection replaces history', () => {
    const { result } = setup('/organizations/7?settings=profile');
    expect(result.current.navigationType).toBe('POP');
    act(() => result.current.param.setSection('admins'));
    expect(search(result).get('settings')).toBe('admins');
    expect(result.current.navigationType).toBe('REPLACE');
  });

  it('openSettings pushes a history entry', () => {
    const { result } = setup('/organizations/7');
    act(() => result.current.param.openSettings());
    expect(result.current.navigationType).toBe('PUSH');
  });

  it('Back after openSettings closes the modal on the same page', () => {
    const { result } = setup('/organizations/7');
    act(() => result.current.param.openSettings());
    act(() => result.current.navigate(-1));
    expect(result.current.location.pathname).toBe('/organizations/7');
    expect(result.current.param.open).toBe(false);
  });

  it('close replaces history', () => {
    const { result } = setup('/organizations/7?settings=admins');
    act(() => result.current.param.close());
    expect(result.current.navigationType).toBe('REPLACE');
  });

  it('rewrites a legacy URL reached by a later navigation', () => {
    const { result } = setup('/organizations/7?tab=settings&section=admins');
    expect(search(result).get('settings')).toBe('admins');
    act(() => result.current.param.close());
    act(() => result.current.navigate('/organizations/7?tab=settings'));
    expect(search(result).has('tab')).toBe(false);
    expect(search(result).get('settings')).toBe('');
  });
});
