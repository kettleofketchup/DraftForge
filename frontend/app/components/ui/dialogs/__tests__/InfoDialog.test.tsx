// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { useState } from 'react';
import { describe, expect, it } from 'vitest';
import { SecondaryButton } from '~/components/ui/buttons';
import { InfoDialog } from '../InfoDialog';

describe('InfoDialog', () => {
  it('forwards close autofocus cancellation', async () => {
    const cancelled: boolean[] = [];
    function Harness() {
      const [open, setOpen] = useState(false);
      return (
        <>
          <SecondaryButton onClick={() => setOpen(true)}>
            Open info
          </SecondaryButton>
          <InfoDialog
            open={open}
            onOpenChange={setOpen}
            title="Information"
            onCloseAutoFocus={(event) => {
              event.preventDefault();
              cancelled.push(event.defaultPrevented);
              screen.getByTestId('destination').focus();
            }}
          >
            <p>Details</p>
          </InfoDialog>
          <input data-testid="destination" aria-label="Destination" />
        </>
      );
    }
    render(<Harness />);
    fireEvent.click(screen.getByRole('button', { name: 'Open info' }));
    fireEvent.click(screen.getAllByRole('button', { name: 'Close' })[0]);
    await waitFor(() => expect(cancelled).toEqual([true]));
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(screen.getByTestId('destination')).toHaveFocus();
  });
});
