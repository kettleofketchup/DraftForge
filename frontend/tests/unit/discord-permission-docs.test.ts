import { existsSync, readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

import {
  ActionKindSchema,
  BlockerSchema,
  PermissionCheckResultSchema,
} from '~/features/discord-permissions/api.generated';

const GUIDE = fileURLToPath(
  new URL(
    '../../../docs/features/events/discord-permissions.md',
    import.meta.url,
  ),
);
const MKDOCS = fileURLToPath(new URL('../../../mkdocs.yml', import.meta.url));

const guide = (): string => {
  expect(existsSync(GUIDE)).toBe(true);
  return readFileSync(GUIDE, 'utf8');
};

describe('Discord permission badges guide', () => {
  it('documents every public status', () => {
    const text = guide();
    for (const status of PermissionCheckResultSchema.shape.status.options) {
      expect(text).toContain(`\`${status}\``);
    }
  });

  it('documents every action kind', () => {
    const text = guide();
    for (const action of ActionKindSchema.options) {
      expect(text).toContain(`\`${action}\``);
    }
  });

  it('documents every reason code and blocker', () => {
    const text = guide();
    const reasons = PermissionCheckResultSchema.shape.reason.options[0].options;
    for (const code of [...reasons, ...BlockerSchema.shape.code.options]) {
      expect(text).toContain(`\`${code}\``);
    }
  });

  it('states the delivery limitation', () => {
    expect(guide()).toContain('does not guarantee delivery');
  });

  it('is in the mkdocs navigation', () => {
    expect(readFileSync(MKDOCS, 'utf8')).toContain(
      'features/events/discord-permissions.md',
    );
  });
});
