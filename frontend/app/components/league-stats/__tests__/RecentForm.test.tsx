// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { RecentForm } from '../RecentForm';

const slots = () =>
  Array.from(screen.getByTestId('recent-form').children) as HTMLElement[];

afterEach(cleanup);

describe('RecentForm', () => {
  it('pads empty slots on the left', () => {
    render(<RecentForm results={['W', 'L']} count={5} />);
    const all = slots();
    expect(all.map((s) => s.dataset.result)).toEqual([
      'empty',
      'empty',
      'empty',
      'W',
      'L',
    ]);
    const empty = all[0];
    expect(empty.children).toHaveLength(1);
    expect(empty.className).not.toMatch(/\bborder\b/);
    expect(all[4].className).toContain('border-destructive');
    expect(all[3].className).toContain('bg-success');
  });

  it('takes the newest count results', () => {
    render(
      <RecentForm results={['L', 'L', 'W', 'W', 'L', 'W', 'L']} count={5} />,
    );
    expect(slots().map((s) => s.dataset.result)).toEqual([
      'W',
      'W',
      'L',
      'W',
      'L',
    ]);
  });

  it('labels the group oldest to newest', () => {
    render(<RecentForm results={['L', 'W', 'L', 'L', 'L', 'W']} count={5} />);
    const group = screen.getByRole('img');
    expect(group.getAttribute('aria-label')).toBe(
      'Last 5: W L L L W, oldest to newest',
    );
  });

  it('announces empty slots as a count', () => {
    render(<RecentForm results={['W', 'L']} count={5} />);
    expect(screen.getByRole('img').getAttribute('aria-label')).toBe(
      'Last 5: W L, oldest to newest (3 no game yet)',
    );
  });

  it('gives every slot a title', () => {
    render(<RecentForm results={['W', 'L']} count={3} />);
    expect(slots().map((s) => s.getAttribute('title'))).toEqual([
      'No game yet',
      'Win',
      'Loss',
    ]);
  });
});
