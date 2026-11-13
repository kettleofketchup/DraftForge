// @vitest-environment jsdom
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { TooltipProvider } from '~/components/ui/tooltip';
import { DeleteDialog } from '../DeleteDialog';
import { FormDialog } from '../FormDialog';

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??= ResizeObserverStub as unknown as typeof ResizeObserver;

// EditLeagueModal renders DeleteLeagueDialog inside FormDialog's children.
// The delete dialog is portaled out of the form's DOM, but React still bubbles
// its events up the component tree into FormDialog.
function setup() {
  const onSubmit = vi.fn();
  const onConfirm = vi.fn();
  render(
    <TooltipProvider>
      <FormDialog open onOpenChange={vi.fn()} title="Edit League" onSubmit={onSubmit}>
        <input data-testid="league-name" defaultValue="Acme League" />
        <DeleteDialog
          open
          onOpenChange={vi.fn()}
          entityKind="League"
          entityName="Acme League"
          onConfirm={onConfirm}
          inputTestId="dd-input"
          confirmTestId="dd-confirm"
        />
      </FormDialog>
    </TooltipProvider>,
  );
  return { onSubmit, onConfirm };
}

describe('DeleteDialog nested in FormDialog', () => {
  it('Enter in the confirm-name input does not submit the outer form', () => {
    const { onSubmit } = setup();
    const input = screen.getByTestId('dd-input');
    fireEvent.change(input, { target: { value: 'Acme League' } });
    fireEvent.keyDown(input, { key: 'Enter' });

    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('Enter in the confirm-name input deletes once the name matches', () => {
    const { onConfirm } = setup();
    const input = screen.getByTestId('dd-input');
    fireEvent.change(input, { target: { value: 'Acme League' } });
    fireEvent.keyDown(input, { key: 'Enter' });

    expect(onConfirm).toHaveBeenCalledOnce();
  });

  it('Enter does not delete while the name does not match', () => {
    const { onConfirm, onSubmit } = setup();
    const input = screen.getByTestId('dd-input');
    fireEvent.change(input, { target: { value: 'Acme' } });
    fireEvent.keyDown(input, { key: 'Enter' });

    expect(onConfirm).not.toHaveBeenCalled();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('clicking confirm deletes without submitting the outer form', () => {
    const { onConfirm, onSubmit } = setup();
    fireEvent.change(screen.getByTestId('dd-input'), { target: { value: 'Acme League' } });
    fireEvent.click(screen.getByTestId('dd-confirm'));

    expect(onConfirm).toHaveBeenCalledOnce();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('Enter in the outer form still submits it', () => {
    const { onSubmit } = setup();
    fireEvent.keyDown(screen.getByTestId('league-name'), { key: 'Enter' });

    expect(onSubmit).toHaveBeenCalledOnce();
  });
});
