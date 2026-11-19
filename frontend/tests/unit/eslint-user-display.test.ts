import tsParser from '@typescript-eslint/parser';
import type { Rule } from 'eslint';
import { RuleTester } from 'eslint';
import { describe, it } from 'vitest';

import plugin from '../../eslint-rules/user-display.js';

RuleTester.describe = describe;
RuleTester.it = it;
RuleTester.itOnly = it.only;

const tester = new RuleTester({
  languageOptions: {
    parser: tsParser,
    parserOptions: { ecmaFeatures: { jsx: true } },
  },
});

const rule = (name: string): Rule.RuleModule =>
  plugin.rules?.[name] as Rule.RuleModule;

tester.run('use-display-name', rule('use-display-name'), {
  valid: [
    'const a = <span>{DisplayName(p)}</span>;',
    "const a = <span>{p.username ? DisplayName(p) : 'Steam'}</span>;",
    'const a = <span data-testid={`row-${p.username}`}>{p.pk}</span>;',
    'const a = <li key={p.username}>{p.pk}</li>;',
    'log.debug(`removing ${p.username}`);',
    'logger.info(`x ${p.nickname}`);',
    "const q = { queryKey: ['user', `${p.username}`] };",
    'const url = `/users/${p.pk}`;',
    'const n = 1 + p.username;',
    'const a = <span>{team.name}</span>;',
    'const a = <span>{p.username && <b>x</b>}</span>;',
  ],
  invalid: [
    {
      code: 'const a = <span>{p.username}</span>;',
      errors: [{ messageId: 'raw', data: { field: 'username' } }],
    },
    {
      code: 'const a = <span>{p.nickname || p.username}</span>;',
      errors: [{ messageId: 'raw' }, { messageId: 'raw' }],
    },
    {
      code: "const a = <>{p?.guildNickname ?? 'x'}</>;",
      errors: [{ messageId: 'raw', data: { field: 'guildNickname' } }],
    },
    {
      code: 'const a = <span>{ok ? p.discordNickname : null}</span>;',
      errors: [{ messageId: 'raw', data: { field: 'discordNickname' } }],
    },
    {
      code: 'const a = <span>{`by ${p.username}`}</span>;',
      errors: [{ messageId: 'raw' }],
    },
    {
      code: 'const a = <span>{show && p.username}</span>;',
      errors: [{ messageId: 'raw' }],
    },
    {
      code: 'const a = <span title={p.username}>{p.pk}</span>;',
      errors: [{ messageId: 'raw', data: { field: 'username' } }],
    },
    {
      code: 'const a = <img alt={`${p.discordNickname} avatar`} />;',
      errors: [{ messageId: 'raw', data: { field: 'discordNickname' } }],
    },
    {
      code: 'toast.success(`${user.username} has been removed`);',
      errors: [{ messageId: 'raw', data: { field: 'username' } }],
    },
    {
      code: "const msg = 'Removing ' + user.nickname;",
      errors: [{ messageId: 'raw', data: { field: 'nickname' } }],
    },
    {
      code: 'const a = <button onClick={() => toast(`Hi ${u.username}`)} />;',
      errors: [{ messageId: 'raw', data: { field: 'username' } }],
    },
    {
      code: 'const names = users.map((u) => `${u.username}`);',
      errors: [{ messageId: 'raw' }],
    },
  ],
});

tester.run('no-display-org-arg', rule('no-display-org-arg'), {
  valid: ['DisplayName(p);', 'DisplayName(p, 12);', 'other(p, 1, orgId);'],
  invalid: [
    {
      code: 'DisplayName(p, undefined, orgId);',
      errors: [{ messageId: 'explicit' }],
    },
    { code: 'DisplayName(p, 10, null);', errors: [{ messageId: 'explicit' }] },
  ],
});

tester.run('no-user-reshape', rule('no-user-reshape'), {
  valid: [
    'const a = <UserAvatar user={player} />;',
    'const a = <UserAvatar user={player.user} />;',
    'const a = <UserAvatar user={{ pk: a.pk, avatar: b.avatar }} />;',
    "const a = <UserAvatar user={{ pk: 1, username: 'x' }} />;",
    'const a = <Other user={{ pk: p.pk }} />;',
    'const a = <UserAvatar user={{ username: payload.captain_name }} />;',
  ],
  invalid: [
    {
      code: 'const a = <UserAvatar user={{ pk: p.user_id ?? undefined, username: p.username, avatar: p.avatar }} />;',
      errors: [{ messageId: 'reshape', data: { root: 'p' } }],
    },
    {
      code: 'const a = <UserAvatar user={{ pk: row.member.pk, avatar: row.member.avatar }} />;',
      errors: [{ messageId: 'reshape', data: { root: 'row.member' } }],
    },
  ],
});

tester.run('no-direct-name-resolver', rule('no-direct-name-resolver'), {
  valid: ['DisplayName(p);', 'const x = obj.resolveDisplayName;'],
  invalid: [
    { code: 'resolveDisplayName(p);', errors: [{ messageId: 'direct' }] },
    { code: 'const u = AvatarUrl(p);', errors: [{ messageId: 'direct' }] },
  ],
});

tester.run('use-user-avatar', rule('use-user-avatar'), {
  valid: [
    'const a = <AvatarImage src={org.logo} />;',
    'const a = <AvatarImage src="/static/x.png" />;',
    'const a = <UserAvatar user={p} />;',
  ],
  invalid: [
    {
      code: 'const a = <AvatarImage src={p.avatarUrl} />;',
      errors: [{ messageId: 'raw' }],
    },
    {
      code: 'const a = <AvatarImage src={player.avatar || undefined} />;',
      errors: [{ messageId: 'raw' }],
    },
    {
      code: 'const a = <AvatarImage src={claim.claimer_avatar} />;',
      errors: [{ messageId: 'raw' }],
    },
    {
      code: 'const a = <AvatarImage src={avatarUrl ?? undefined} />;',
      errors: [{ messageId: 'raw' }],
    },
    {
      code: 'const a = <AvatarImage src={`https://cdn/x/${u.discordId}/${u.avatar}.png`} />;',
      errors: [{ messageId: 'raw' }],
    },
  ],
});

tester.run('no-avatar-fallback', rule('no-avatar-fallback'), {
  valid: [
    'const a = <UserAvatar user={team.captain} fallbackName={team.name} />;',
    'const a = <Avatar><AvatarFallback>{team.name.slice(0, 2)}</AvatarFallback></Avatar>;',
    'const a = <AvatarFallback>{team.team_name.charAt(0)}</AvatarFallback>;',
    'const a = <Avatar><AvatarFallback>{initials}</AvatarFallback></Avatar>;',
    'const a = ok ? <UserAvatar user={u} /> : <Spinner />;',
    'const a = org.logo ? <Avatar><AvatarImage src={org.logo} /></Avatar> : <Avatar />;',
  ],
  invalid: [
    {
      code: 'const a = team.captain ? <UserAvatar user={team.captain} /> : <Avatar><AvatarFallback>{initials}</AvatarFallback></Avatar>;',
      errors: [{ messageId: 'branch' }],
    },
    {
      code: 'const a = !u ? <Avatar /> : <UserAvatar user={u} />;',
      errors: [{ messageId: 'branch' }],
    },
    {
      code: 'const a = <Avatar><AvatarFallback>{p.username.slice(0, 2)}</AvatarFallback></Avatar>;',
      errors: [{ messageId: 'initials' }],
    },
    {
      code: 'const a = <AvatarFallback>{DisplayName(p).charAt(0)}</AvatarFallback>;',
      errors: [{ messageId: 'initials' }],
    },
    {
      code: 'const a = <AvatarFallback>{claim.claimer_username.charAt(0)}</AvatarFallback>;',
      errors: [{ messageId: 'initials' }],
    },
    {
      code: 'const a = <AvatarFallback>{displayName.substring(0, 2)}</AvatarFallback>;',
      errors: [{ messageId: 'initials' }],
    },
  ],
});
