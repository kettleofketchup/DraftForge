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
    'const a = <span title={p.username}>{p.pk}</span>;',
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
      code: 'const a = <AvatarImage src={`https://cdn/x/${u.discordId}/${u.avatar}.png`} />;',
      errors: [{ messageId: 'raw' }],
    },
  ],
});
