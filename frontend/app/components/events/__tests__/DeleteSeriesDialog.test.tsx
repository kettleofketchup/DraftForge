// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { TooltipProvider } from '~/components/ui/tooltip';
import { DeleteSeriesDialog } from '../DeleteSeriesDialog';

describe('DeleteSeriesDialog', () => {
  it('says which of the series events the delete removes and which it keeps', () => {
    render(
      <TooltipProvider>
        <DeleteSeriesDialog
          open
          onOpenChange={vi.fn()}
          seriesName="Weekly Inhouse"
          onConfirm={vi.fn()}
        />
      </TooltipProvider>,
    );

    const text = screen.getByTestId('delete-series-dialog').textContent ?? '';
    expect(text).toContain(
      'upcoming events and events with signups or roll call open are deleted',
    );
    expect(text).toContain(
      'In-progress, completed and cancelled events are kept.',
    );
    expect(text).not.toMatch(/already been generated are preserved/);
  });
});
