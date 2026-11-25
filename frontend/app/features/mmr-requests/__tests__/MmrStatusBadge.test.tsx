// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { MmrStatusBadge } from '../MmrStatusBadge';

describe('MmrStatusBadge', () => {
  it('shows official with the verifier and date', () => {
    render(
      <MmrStatusBadge
        verified
        verifiedBy="staffy"
        verifiedAt="2026-11-22T10:00:00Z"
      />,
    );
    expect(screen.getByTestId('mmr-badge-official')).toHaveTextContent(
      'Official',
    );
    expect(screen.getByTestId('mmr-badge-verifier')).toHaveTextContent(
      'by staffy · 22 Nov 2026',
    );
    expect(screen.queryByTestId('mmr-badge-unverified')).toBeNull();
  });

  it('shows a legacy official without a verifier', () => {
    render(<MmrStatusBadge verified legacy />);
    const badge = screen.getByTestId('mmr-badge-official');
    expect(badge).toHaveAttribute(
      'title',
      expect.stringContaining('before review history'),
    );
    expect(screen.queryByTestId('mmr-badge-verifier')).toBeNull();
  });

  it('shows unverified', () => {
    render(<MmrStatusBadge verified={false} />);
    expect(screen.getByTestId('mmr-badge-unverified')).toHaveTextContent(
      'Unverified',
    );
    expect(screen.queryByTestId('mmr-badge-official')).toBeNull();
    expect(screen.queryByTestId('mmr-badge-pending')).toBeNull();
  });

  it('adds a pending badge', () => {
    render(<MmrStatusBadge verified={false} pending />);
    expect(screen.getByTestId('mmr-badge-unverified')).toBeInTheDocument();
    expect(screen.getByTestId('mmr-badge-pending')).toHaveTextContent(
      'Pending',
    );
  });
});
