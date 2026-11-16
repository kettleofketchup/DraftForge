// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  REFRESH_MIN_INTERVAL_MS,
  activityAuthorization,
  activityExternalUrl,
  activitySocket,
  getActivityCredential,
  isActivityFrame,
  refreshActivityCredential,
  setActivityCredential,
  setActivityRefreshExhausted,
  setActivityRefresher,
  toActivityCredential,
  type ActivityCredential,
} from './activity-session';
import type { DraftActivitySession } from './discord';

const tournament: ActivityCredential = {
  token: 'secret',
  scope: 'tournament',
  tournament_id: 12,
  pin: null,
  site_url: 'https://site.test',
};
const heroPin: ActivityCredential = {
  token: 'secret',
  scope: 'draft',
  tournament_id: null,
  pin: { kind: 'hero', id: 7 },
  site_url: 'https://site.test',
};
const teamPin: ActivityCredential = {
  ...heroPin,
  pin: { kind: 'team', id: 9 },
};
const AUTH = 'DraftActivity secret';

afterEach(() => setActivityCredential(null));
describe('Activity credentials', () => {
  it('preserves website sockets and sends no Activity authorization by default', () => {
    expect(activitySocket('hero', 7).url).toContain('/api/herodraft/7/');
    expect(activitySocket('team', 7).url).toContain('/api/draft/7/');
    expect(activitySocket('team', 7).protocols).toBeUndefined();
    expect(activityAuthorization('/current_user')).toBeUndefined();
    expect(getActivityCredential()).toBeNull();
  });
  it('attaches a tournament credential to every allowlisted draft path', () => {
    setActivityCredential(tournament);
    for (const path of [
      '/herodraft/9/',
      '/herodraft/9/submit-pick/',
      '/herodraft/9/list-available-heroes/',
      '/draft/4/ready/',
      '/draft/4/pause/',
      '/tournaments/pick_player',
      '/tournaments/undo-pick',
      '/draft/get-style-mmrs',
      '/discord/activity/drafts/',
      '/discord/activity/views/',
      '/current_user',
    ])
      expect(activityAuthorization(path), path).toBe(AUTH);
  });
  it('never attaches to destructive or anonymous paths', () => {
    setActivityCredential(tournament);
    for (const path of [
      '/herodraft/9/reset/',
      '/herodraft/9/abandon/',
      '/herodraft/9/ssr/',
      '/tournaments/12/',
      '/bracket/12/',
      '/draft/4/',
      '/tournaments/init-draft',
      '/users/1/',
      '/herodraft/0x9/',
    ])
      expect(activityAuthorization(path), path).toBeUndefined();
  });
  it('limits a draft-scope credential to its pinned hero draft', () => {
    setActivityCredential(heroPin);
    expect(activityAuthorization('/herodraft/7/submit-pick/')).toBe(AUTH);
    expect(activityAuthorization('/herodraft/8/submit-pick/')).toBeUndefined();
    expect(activityAuthorization('/tournaments/pick_player')).toBeUndefined();
    expect(activityAuthorization('/current_user')).toBe(AUTH);
    expect(activityAuthorization('/discord/activity/drafts/')).toBe(AUTH);
    const socket = activitySocket('hero', 7);
    expect(socket.url).toContain('/api/discord/activity/draft/7/');
    expect(socket.url).not.toContain('secret');
    expect(socket.protocols).toEqual(['draftactivity', 'secret']);
    expect(activitySocket('hero', 8).protocols).toBeUndefined();
    expect(activitySocket('team', 7).protocols).toBeUndefined();
  });
  it('limits a draft-scope team credential to its pinned team draft', () => {
    setActivityCredential(teamPin);
    expect(activityAuthorization('/draft/9/ready/')).toBe(AUTH);
    expect(activityAuthorization('/draft/10/ready/')).toBeUndefined();
    expect(activityAuthorization('/tournaments/pick_player')).toBe(AUTH);
    expect(activityAuthorization('/tournaments/undo-pick')).toBe(AUTH);
    expect(activityAuthorization('/draft/get-style-mmrs')).toBe(AUTH);
    expect(activitySocket('team', 9).url).toContain(
      '/api/discord/activity/team-draft/9/',
    );
  });
  it('opens Activity sockets for any draft under tournament scope', () => {
    setActivityCredential(tournament);
    const hero = activitySocket('hero', 99);
    expect(hero.url).toContain('/api/discord/activity/draft/99/');
    expect(hero.protocols).toEqual(['draftactivity', 'secret']);
    expect(activitySocket('team', 40).url).toContain(
      '/api/discord/activity/team-draft/40/',
    );
  });
  it('builds browser links from the site URL, not the proxied origin', () => {
    setActivityCredential(tournament);
    expect(activityExternalUrl({ kind: 'hero', id: 156 })).toBe(
      'https://site.test/herodraft/156',
    );
    expect(activityExternalUrl({ kind: 'team', id: 40 })).toBe(
      'https://site.test/tournament/12/teams/draft',
    );
    expect(activityExternalUrl({ kind: 'bracket' })).toBe(
      'https://site.test/tournament/12/bracket',
    );
    setActivityCredential(heroPin);
    expect(activityExternalUrl({ kind: 'hero', id: 7 })).toBe(
      'https://site.test/herodraft/7',
    );
    expect(activityExternalUrl({ kind: 'bracket' })).toBeUndefined();
    setActivityCredential(null);
    expect(activityExternalUrl({ kind: 'hero', id: 7 })).toBeUndefined();
  });
  it('detects the Activity frame from the path', () => {
    window.history.replaceState(null, '', '/activity?frame_id=f');
    expect(isActivityFrame()).toBe(true);
    window.history.replaceState(null, '', '/tournament/1');
    expect(isActivityFrame()).toBe(false);
  });
});

describe('Session to credential', () => {
  const base = {
    token: 't',
    draft_id: 40,
    kind: 'team',
    tournament_id: 12,
    user: { pk: 1 },
  } as DraftActivitySession;
  it('keeps tournament scope without a pin', () => {
    expect(
      toActivityCredential({
        ...base,
        scope: 'tournament',
        site_url: 'https://site.test',
      }),
    ).toEqual({
      token: 't',
      scope: 'tournament',
      tournament_id: 12,
      pin: null,
      site_url: 'https://site.test',
      user: { pk: 1 },
    });
  });
  it('pins an older backend response to its legacy draft', () => {
    const credential = toActivityCredential(base);
    expect(credential.scope).toBe('draft');
    expect(credential.pin).toEqual({ kind: 'team', id: 40 });
    expect(credential.site_url).toBeNull();
    setActivityCredential(credential);
    expect(activityExternalUrl({ kind: 'team', id: 40 })).toBeUndefined();
    expect(activityExternalUrl({ kind: 'hero', id: 7 })).toBeUndefined();
    setActivityCredential(null);
  });
  it('pins the draft-scope fallback to the legacy draft', () => {
    expect(
      toActivityCredential({ ...base, scope: 'draft', tournament_id: null })
        .pin,
    ).toEqual({ kind: 'team', id: 40 });
  });
});

describe('Activity credential refresh', () => {
  afterEach(() => {
    setActivityRefresher(null);
    setActivityRefreshExhausted(null);
    vi.useRealTimers();
  });
  it('shares one handshake between sockets and reports failure', async () => {
    vi.useFakeTimers();
    let finish!: () => void;
    const refresher = vi.fn(
      () => new Promise<void>((resolve) => (finish = resolve)),
    );
    setActivityRefresher(refresher);
    const first = refreshActivityCredential();
    const second = refreshActivityCredential();
    finish();
    expect(await first).toBe(true);
    expect(await second).toBe(true);
    expect(refresher).toHaveBeenCalledOnce();
    vi.advanceTimersByTime(REFRESH_MIN_INTERVAL_MS);
    setActivityRefresher(() => Promise.reject(new Error('expired')));
    expect(await refreshActivityCredential()).toBe(false);
    setActivityRefresher(null);
    expect(await refreshActivityCredential()).toBe(false);
  });
  it('refuses a second refresh within 30 seconds', async () => {
    vi.useFakeTimers();
    const refresher = vi.fn(async () => {});
    setActivityRefresher(refresher);
    expect(await refreshActivityCredential()).toBe(true);
    vi.advanceTimersByTime(10_000);
    expect(await refreshActivityCredential()).toBe(false);
    expect(refresher).toHaveBeenCalledOnce();
  });
  it('stops after three refreshes in ten minutes and reports exhaustion', async () => {
    vi.useFakeTimers();
    const refresher = vi.fn(async () => {});
    const exhausted = vi.fn();
    setActivityRefresher(refresher);
    setActivityRefreshExhausted(exhausted);
    for (let i = 0; i < 3; i++) {
      expect(await refreshActivityCredential()).toBe(true);
      vi.advanceTimersByTime(60_000);
    }
    expect(exhausted).not.toHaveBeenCalled();
    expect(await refreshActivityCredential()).toBe(false);
    expect(refresher).toHaveBeenCalledTimes(3);
    expect(exhausted).toHaveBeenCalledOnce();
  });
  it('allows refreshes again once the ten-minute window has passed', async () => {
    vi.useFakeTimers();
    const refresher = vi.fn(async () => {});
    setActivityRefresher(refresher);
    for (let i = 0; i < 3; i++) {
      await refreshActivityCredential();
      vi.advanceTimersByTime(60_000);
    }
    vi.advanceTimersByTime(600_000);
    expect(await refreshActivityCredential()).toBe(true);
    expect(refresher).toHaveBeenCalledTimes(4);
  });
});
