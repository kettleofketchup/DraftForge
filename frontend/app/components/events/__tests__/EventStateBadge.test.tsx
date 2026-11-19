// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { EventStateBadge } from '../EventStateBadge';

describe('EventStateBadge', () => {
  it('labels a dropped signup', () => {
    render(<EventStateBadge state="dropped" data-testid="badge" />);
    expect(screen.getByTestId('badge').textContent).toBe('Dropped');
  });

  it('styles dropped like the other removed statuses', () => {
    render(<EventStateBadge state="dropped" data-testid="badge" />);
    expect(screen.getByTestId('badge').className).toContain('text-error');
  });
});
