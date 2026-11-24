// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { TeamStatusBadge } from '../TeamStatusBadge';
import { ordinal, teamStatus, teamStatusLabel } from '../teamStatus';

const RAW_PALETTE =
  /\b(?:bg|text|border)-(?:red|green|blue|purple|violet|emerald|rose|orange|amber|cyan|teal)-\d/;

describe('ordinal', () => {
  it.each([
    [1, '1st'],
    [2, '2nd'],
    [3, '3rd'],
    [4, '4th'],
    [11, '11th'],
    [12, '12th'],
    [13, '13th'],
    [21, '21st'],
    [22, '22nd'],
    [101, '101st'],
    [111, '111th'],
  ])('%i -> %s', (n, expected) => {
    expect(ordinal(n)).toBe(expected);
  });
});

describe('teamStatus', () => {
  it('treats null and undefined as live', () => {
    expect(teamStatus(null)).toBe('live');
    expect(teamStatus(undefined)).toBe('live');
  });

  it('treats placement 1 as winner', () => {
    expect(teamStatus(1)).toBe('winner');
  });

  it('treats other placements as eliminated', () => {
    expect(teamStatus(2)).toBe('eliminated');
    expect(teamStatus(4)).toBe('eliminated');
  });
});

describe('teamStatusLabel', () => {
  it('labels each status', () => {
    expect(teamStatusLabel(null)).toBe('In tournament');
    expect(teamStatusLabel(undefined)).toBe('In tournament');
    expect(teamStatusLabel(1)).toBe('Winner');
    expect(teamStatusLabel(2)).toBe('Eliminated · 2nd');
  });
});

describe('TeamStatusBadge', () => {
  it.each([
    [null, 'live', 'In tournament'],
    [1, 'winner', 'Winner'],
    [4, 'eliminated', 'Eliminated · 4th'],
  ] as const)('placement %s renders %s', (placement, status, text) => {
    render(<TeamStatusBadge placement={placement} />);
    const badge = screen.getByTestId('team-status-badge');
    expect(badge).toHaveAttribute('data-status', status);
    expect(badge).toHaveTextContent(text);
    expect(badge.className).not.toMatch(RAW_PALETTE);
  });

  it('merges a custom className', () => {
    render(<TeamStatusBadge placement={null} className="ml-2" />);
    expect(screen.getByTestId('team-status-badge')).toHaveClass('ml-2');
  });
});
