// @vitest-environment jsdom
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { DisplayName } from '~/index';
import { DraftPauseOverlay } from '../timer/DraftPauseOverlay';
import { user } from './fixtures';

const base = { draftStatus: 'paused' as const, isManualPause: false, resumingRemainingMs: 0, activeCaptain: user(7), isActiveCaptainDisconnected: false, canResume: true, isStaff: false, onResume: vi.fn(), onPickForCaptain: vi.fn() };

describe('DraftPauseOverlay', () => {
  it('renders nothing while drafting', () => { const { container } = render(<DraftPauseOverlay {...base} draftStatus="drafting" />); expect(container).toBeEmptyDOMElement(); });
  it('resume enabled when the active captain is fresh', () => { render(<DraftPauseOverlay {...base} />); expect(screen.getByTestId('draft-resume-button')).toBeEnabled(); });
  it('resume shown but disabled while the active captain is stale; staff see Pick for captain', () => {
    const { rerender } = render(<DraftPauseOverlay {...base} isActiveCaptainDisconnected />);
    expect(screen.getByTestId('draft-resume-button')).toBeDisabled();
    expect(screen.getByTestId('draft-paused-message')).toHaveTextContent(`${DisplayName(user(7))} is disconnected — pick for them or wait`);
    expect(screen.queryByTestId('draft-pick-for-captain-button')).toBeNull();
    rerender(<DraftPauseOverlay {...base} isActiveCaptainDisconnected isStaff />);
    expect(screen.getByTestId('draft-pick-for-captain-button')).toBeVisible();
  });
  it('Pick for captain minimises the overlay to a banner that leaves the player list reachable', () => {
    const onPickForCaptain = vi.fn();
    const { rerender } = render(<DraftPauseOverlay {...base} isActiveCaptainDisconnected isStaff onPickForCaptain={onPickForCaptain} />);
    fireEvent.click(screen.getByTestId('draft-pick-for-captain-button'));
    expect(onPickForCaptain).toHaveBeenCalledTimes(1);
    expect(screen.queryByTestId('draft-paused-overlay')).toBeNull();
    expect(screen.getByTestId('draft-paused-banner')).toBeVisible();
    expect(screen.getByTestId('draft-resume-button')).toBeDisabled();
    fireEvent.click(screen.getByTestId('draft-paused-expand'));
    expect(screen.getByTestId('draft-paused-overlay')).toBeVisible();
    fireEvent.click(screen.getByTestId('draft-pick-for-captain-button'));
    rerender(<DraftPauseOverlay {...base} draftStatus="drafting" isStaff onPickForCaptain={onPickForCaptain} />);
    rerender(<DraftPauseOverlay {...base} isActiveCaptainDisconnected isStaff onPickForCaptain={onPickForCaptain} />);
    expect(screen.getByTestId('draft-paused-overlay')).toBeVisible();
  });
  it('spectators get no Resume button', () => { render(<DraftPauseOverlay {...base} canResume={false} />); expect(screen.queryByTestId('draft-resume-button')).toBeNull(); });
  it('resuming shows the countdown', () => { render(<DraftPauseOverlay {...base} draftStatus="resuming" resumingRemainingMs={2_400} />); expect(screen.getByTestId('draft-resuming-countdown')).toHaveTextContent('Resuming in 3'); });
});

describe('DraftPauseOverlay rejected resume', () => {
  it('swallows a rejected onResume instead of leaving it unhandled', async () => {
    const onResume = vi.fn().mockRejectedValue(new Error('boom'));
    render(
      <DraftPauseOverlay
        draftStatus="paused"
        isManualPause
        resumingRemainingMs={0}
        activeCaptain={null}
        isActiveCaptainDisconnected={false}
        canResume
        isStaff={false}
        onResume={onResume}
        onPickForCaptain={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByTestId('draft-resume-button'));
    await Promise.resolve();
    await Promise.resolve();
    expect(onResume).toHaveBeenCalledTimes(1);
  });
});
