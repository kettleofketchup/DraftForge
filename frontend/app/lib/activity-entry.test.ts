import { describe, expect, it } from 'vitest';
import { activityEntryPath } from './activity-entry';

describe('Discord root entry', () => {
  it('preserves every SDK parameter while routing to the Activity', () => {
    const query =
      '?frame_id=f&instance_id=i&platform=desktop&channel_id=12&guild_id=34&custom=a%2Fb';
    expect(activityEntryPath('/', query)).toBe(`/activity${query}`);
  });
  it('leaves website visits and already-routed Activities unchanged', () => {
    expect(activityEntryPath('/', '')).toBeNull();
    expect(activityEntryPath('/', '?frame_id=f')).toBeNull();
    expect(activityEntryPath('/', '?campaign=discord')).toBeNull();
    expect(
      activityEntryPath('/activity', '?frame_id=f&instance_id=i'),
    ).toBeNull();
  });
});
