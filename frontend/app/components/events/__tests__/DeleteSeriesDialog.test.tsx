// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { TooltipProvider } from '~/components/ui/tooltip';
import { DeleteSeriesDialog } from '../DeleteSeriesDialog';

function renderDialog(onConfirm = vi.fn()) {
  render(
    <TooltipProvider>
      <DeleteSeriesDialog
        open
        onOpenChange={vi.fn()}
        seriesName="Weekly Night"
        onConfirm={onConfirm}
      />
    </TooltipProvider>,
  );
  return onConfirm;
}

describe('DeleteSeriesDialog', () => {
  it('explains which occurrences are cancelled, deleted and kept', () => {
    renderDialog();
    const text = screen.getByTestId('delete-series-dialog').textContent ?? '';
    expect(text).toContain(
      'Upcoming, signups-open and roll-call occurrences with sign-ups or historical signup records are cancelled and kept.',
    );
    expect(text).toContain(
      'Empty upcoming, signups-open and roll-call occurrences are deleted',
    );
    expect(text).toContain(
      'In-progress, completed and already-cancelled occurrences are kept.',
    );
    expect(text).not.toMatch(
      /events with signups or roll call open are deleted/,
    );
  });

  it('requires the exact name and awaits confirmation', async () => {
    let resolve!: () => void;
    const onConfirm = renderDialog(
      vi.fn(() => new Promise<void>((done) => (resolve = done))),
    );
    const confirm = screen.getByTestId('delete-series-confirm');
    fireEvent.change(screen.getByTestId('delete-series-confirm-input'), {
      target: { value: 'Weekly' },
    });
    expect(confirm).toBeDisabled();
    fireEvent.change(screen.getByTestId('delete-series-confirm-input'), {
      target: { value: 'Weekly Night' },
    });
    fireEvent.click(confirm);
    expect(onConfirm).toHaveBeenCalledOnce();
    resolve();
    await waitFor(() => expect(onConfirm).toHaveBeenCalledOnce());
  });
});
