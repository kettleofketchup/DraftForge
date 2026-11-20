// @vitest-environment jsdom
import { act, render } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router';
import { describe, expect, it } from 'vitest';
import { useUrlTabs } from '~/components/ui/tabs';
import { useOrgSettingsParam } from '../useOrgSettingsParam';

type Writers = {
  setTab: (value: string) => void;
  openSettings: (section?: string) => void;
};

function setup(loader?: () => Promise<null>) {
  const writers: { current: Writers | null } = { current: null };
  function Page() {
    const [, setTab] = useUrlTabs('leagues');
    const { openSettings } = useOrgSettingsParam({
      settled: true,
      canOpen: true,
    });
    writers.current = { setTab, openSettings };
    return null;
  }
  const router = createMemoryRouter(
    [{ path: '/organizations/:id', Component: Page, loader }],
    {
      initialEntries: ['/organizations/7'],
      hydrationData: loader ? { loaderData: { '0': null } } : undefined,
    },
  );
  render(<RouterProvider router={router} />);
  return { router, writers };
}

const search = (router: ReturnType<typeof createMemoryRouter>) =>
  new URLSearchParams(router.state.location.search);

describe('back-to-back URL param writes', () => {
  it('keeps the tab when settings opens before a re-render', async () => {
    const { router, writers } = setup();
    await act(async () => {
      const { setTab, openSettings } = writers.current!;
      setTab('events');
      openSettings();
    });
    expect(search(router).get('tab')).toBe('events');
    expect(search(router).get('settings')).toBe('');
  });

  it('keeps the tab when settings opens while the tab navigation is loading', async () => {
    let release = () => {};
    let calls = 0;
    const loader = () => {
      calls += 1;
      return calls === 1
        ? new Promise<null>((resolve) => {
            release = () => resolve(null);
          })
        : Promise.resolve(null);
    };
    const { router, writers } = setup(loader);
    await act(async () => writers.current!.setTab('events'));
    expect(router.state.navigation.state).toBe('loading');
    await act(async () => writers.current!.openSettings());
    await act(async () => release());
    expect(search(router).get('tab')).toBe('events');
    expect(search(router).get('settings')).toBe('');
  });
});
