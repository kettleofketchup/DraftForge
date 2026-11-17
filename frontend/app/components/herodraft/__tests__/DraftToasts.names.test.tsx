// @vitest-environment jsdom
import { act, render, screen } from '@testing-library/react';
import { toast, Toaster } from 'sonner';
import { beforeAll, beforeEach, describe, expect, it } from 'vitest';
import { useUserCacheStore } from '~/store/userCacheStore';
import { CaptainToast, HeroActionToast } from '../DraftToasts';

beforeAll(() => {
  window.matchMedia ??= ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
});

const captain = {
  pk: 1,
  username: 'dc_handle',
  avatar: null,
};

beforeEach(() => {
  toast.dismiss();
  useUserCacheStore.getState().reset();
  useUserCacheStore.getState().upsert(
    {
      pk: 1,
      username: 'dc_handle',
      discordNickname: 'GwaihirTheWindlord',
      guildNickname: 'DragonClaw',
    } as never,
    { orgId: 7 },
  );
});

describe('herodraft toasts', () => {
  it('captain toast shows the server nickname for the draft org', async () => {
    render(<Toaster />);
    act(() => {
      toast(<CaptainToast captain={captain} message="is ready" orgId={7} />);
    });
    expect(await screen.findByText('DragonClaw')).toBeTruthy();
  });

  it('hero action toast shows the global name without an org', async () => {
    render(<Toaster />);
    act(() => {
      toast(
        <HeroActionToast
          captain={captain}
          action="picked"
          heroName="Axe"
          orgId={null}
        />,
      );
    });
    expect(await screen.findByText('GwaihirTheWindlord')).toBeTruthy();
  });

  it('falls back to the payload username for an uncached captain', async () => {
    render(<Toaster />);
    act(() => {
      toast(
        <CaptainToast
          captain={{ pk: 99, username: 'stranger', avatar: null }}
          message="joined"
          orgId={7}
        />,
      );
    });
    expect(await screen.findByText('stranger')).toBeTruthy();
  });
});
