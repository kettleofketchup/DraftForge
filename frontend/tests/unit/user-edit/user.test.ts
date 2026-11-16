import { describe, expect, it } from 'vitest';
import { User } from '~/components/user/user';
import type { GuildMember } from '~/index';

const member = {
  nick: 'DragonClaw',
  user: {
    id: '123456789012345678',
    username: 'dragonclaw_user',
    global_name: 'GwaihirTheWindlord',
    avatar: 'abc123',
  },
} as unknown as GuildMember;

describe('User.setFromGuildMember', () => {
  it('does not set guildNickname from the server nick', () => {
    const user = new User({} as never);
    user.setFromGuildMember(member);
    expect(user.guildNickname).toBeUndefined();
  });

  it('sets discordNickname from global_name and leaves nickname unset', () => {
    const user = new User({} as never);
    user.setFromGuildMember(member);
    expect(user.discordNickname).toBe('GwaihirTheWindlord');
    expect(user.nickname).toBeUndefined();
    expect(user.username).toBe('dragonclaw_user');
    expect(user.discordId).toBe('123456789012345678');
  });
});
