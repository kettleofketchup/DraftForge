import { describe, expect, it, vi } from 'vitest';

vi.mock('~/root', () => ({ queryClient: {} }));

import { shouldRevalidate } from '../organization';

type Args = Parameters<typeof shouldRevalidate>[0];

const args = (from: string, to: string, extra: Partial<Args> = {}): Args =>
  ({
    currentUrl: new URL(from, 'https://x'),
    nextUrl: new URL(to, 'https://x'),
    defaultShouldRevalidate: true,
    ...extra,
  }) as Args;

describe('organization shouldRevalidate', () => {
  it('skips the loader when only ?tab changes', () => {
    expect(shouldRevalidate(args('/organizations/8', '/organizations/8?tab=events'))).toBe(false);
    expect(shouldRevalidate(args('/organizations/8?tab=users', '/organizations/8'))).toBe(false);
  });

  it('revalidates when the organization changes', () => {
    expect(shouldRevalidate(args('/organizations/8', '/organizations/9'))).toBe(true);
  });

  it('defers to the default after a form submission', () => {
    expect(
      shouldRevalidate(args('/organizations/8', '/organizations/8', { formMethod: 'POST' })),
    ).toBe(true);
  });
});
