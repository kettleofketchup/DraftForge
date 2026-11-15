// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest';
import {
  activityAuthorization,
  activitySocket,
  setActivityCredential,
} from './activity-session';

afterEach(() => setActivityCredential(null));
describe('Activity credentials', () => {
  it('preserves website sockets and sends no Activity authorization by default', () => {
    expect(activitySocket('hero', 7).url).toContain('/api/herodraft/7/');
    expect(activitySocket('team', 7).url).toContain('/api/draft/7/');
    expect(activitySocket('team', 7).protocols).toBeUndefined();
    expect(activityAuthorization('/current_user')).toBeUndefined();
  });
  it('scopes hero credentials to the assigned draft and keeps secrets out of URLs', () => {
    setActivityCredential({ kind: 'hero', draft_id: 7, token: 'secret' });
    expect(activityAuthorization('/herodraft/7/submit-pick/')).toBe(
      'DraftActivity secret',
    );
    expect(activityAuthorization('/herodraft/8/submit-pick/')).toBeUndefined();
    expect(activityAuthorization('/users/1/')).toBeUndefined();
    const socket = activitySocket('hero', 7);
    expect(socket.url).toContain('/api/discord/activity/draft/7/');
    expect(socket.url).not.toContain('secret');
    expect(socket.protocols).toEqual(['draftactivity', 'secret']);
    expect(activitySocket('team', 7).protocols).toBeUndefined();
  });
  it('supports team picks and readiness without granting unrelated API credentials', () => {
    setActivityCredential({ kind: 'team', draft_id: 9, token: 'secret' });
    expect(activityAuthorization('/draft/9/ready/')).toBe(
      'DraftActivity secret',
    );
    expect(activityAuthorization('/tournaments/pick_player')).toBe(
      'DraftActivity secret',
    );
    expect(activityAuthorization('/tournaments/init-draft')).toBeUndefined();
    expect(activitySocket('team', 9).url).toContain(
      '/api/discord/activity/team-draft/9/',
    );
  });
});
