// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { StreakBadge } from '../StreakBadge';

afterEach(cleanup);

describe('StreakBadge', () => {
  it('renders nothing below 3', () => {
    const { container } = render(
      <StreakBadge streak={{ result: 'W', count: 2 }} />,
    );
    expect(container.innerHTML).toBe('');
  });

  it('renders nothing without a streak', () => {
    const { container } = render(<StreakBadge streak={null} />);
    expect(container.innerHTML).toBe('');
  });

  it('renders W4', () => {
    render(<StreakBadge streak={{ result: 'W', count: 4 }} />);
    const badge = screen.getByTestId('streak-badge');
    expect(badge.textContent).toBe('W4');
    expect(badge.className).toContain('text-success');
    const tokens = badge.className.split(/\s+/);
    expect(tokens).not.toContain('bg-primary');
    expect(tokens).not.toContain('text-primary-foreground');
  });

  it('renders L3', () => {
    render(<StreakBadge streak={{ result: 'L', count: 3 }} />);
    const badge = screen.getByTestId('streak-badge');
    expect(badge.textContent).toBe('L3');
    expect(badge.className).toContain('bg-destructive/25');
    expect(badge.className).toContain('text-foreground');
  });

  it('has no aria-label on the generic span', () => {
    render(<StreakBadge streak={{ result: 'L', count: 3 }} />);
    expect(screen.getByTestId('streak-badge').hasAttribute('aria-label')).toBe(false);
  });

  it('renders W12 without growing the row', () => {
    render(<StreakBadge streak={{ result: 'W', count: 12 }} />);
    const badge = screen.getByTestId('streak-badge');
    expect(badge.textContent).toBe('W12');
    expect(badge.className).toContain('leading-none');
    expect(badge.className).toContain('text-[10px]');
    const tokens = badge.className.split(/\s+/);
    for (const t of ['text-xs', 'py-0.5', 'px-2']) expect(tokens).not.toContain(t);
  });
});
