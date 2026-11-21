// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import type { UserType } from '~/index';
import { RolePositions } from '../index';

const user = {
  positions: { carry: 3, mid: 1, offlane: 2, soft_support: 4, hard_support: 5 },
} as unknown as UserType;

describe('position rank bubble', () => {
  afterEach(cleanup);

  // hover:brightness-125 sets a filter, which makes the badge the bubble's
  // containing block; an overflow-hidden badge would then clip the bubble.
  it.each([1, 2, 3, 4, 5])(
    'anchors rank %i to a non-clipping badge',
    (rank) => {
      render(<RolePositions user={user} disableTooltips />);
      const badge = screen.getByText(String(rank)).parentElement!;
      expect(badge).toHaveAttribute('data-slot', 'badge');
      expect(badge).toHaveClass('relative', 'overflow-visible');
    },
  );
});
