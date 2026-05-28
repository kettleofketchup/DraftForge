// @vitest-environment jsdom
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { TooltipProvider } from '~/components/ui/tooltip';
import { DeleteDialog } from '../DeleteDialog';

// NOTE: Same convention deviation as ConfirmDialog.test.tsx — see that file's
// header comment. @testing-library/react is required here because DeleteDialog
// composes a Radix portal (ConfirmDialog → AlertDialog) and the controlled
// input + name-match gating can only be verified by real DOM rendering.

function setup(props: Partial<React.ComponentProps<typeof DeleteDialog>> = {}) {
  const onConfirm = vi.fn();
  const onOpenChange = vi.fn();
  const utils = render(
    <TooltipProvider>
      <DeleteDialog
        open
        onOpenChange={onOpenChange}
        entityKind="League"
        entityName="Acme League"
        onConfirm={onConfirm}
        confirmTestId="dd-confirm"
        cancelTestId="dd-cancel"
        inputTestId="dd-input"
        contentTestId="dd-content"
        {...props}
      />
    </TooltipProvider>,
  );
  return { ...utils, onConfirm, onOpenChange };
}

describe('DeleteDialog', () => {
  it('disables confirm until input matches entityName exactly', () => {
    setup();
    const confirm = screen.getByTestId('dd-confirm') as HTMLButtonElement;
    expect(confirm).toBeDisabled();

    fireEvent.change(screen.getByTestId('dd-input'), { target: { value: 'acme league' } });
    expect(confirm).toBeDisabled(); // case-sensitive

    fireEvent.change(screen.getByTestId('dd-input'), { target: { value: 'Acme League' } });
    expect(confirm).not.toBeDisabled();
  });

  it('strict equality — no trim on either side', () => {
    setup({ entityName: 'Acme League' });
    fireEvent.change(screen.getByTestId('dd-input'), { target: { value: '  Acme League  ' } });
    expect(screen.getByTestId('dd-confirm')).toBeDisabled();
  });

  it('clears the typed value when open transitions false then true', () => {
    const { rerender } = setup({ entityName: 'X' });
    fireEvent.change(screen.getByTestId('dd-input'), { target: { value: 'X' } });
    expect(screen.getByTestId('dd-input')).toHaveValue('X');

    // Close
    rerender(
      <TooltipProvider>
        <DeleteDialog
          open={false}
          onOpenChange={() => {}}
          entityKind="League"
          entityName="X"
          onConfirm={() => {}}
          inputTestId="dd-input"
        />
      </TooltipProvider>,
    );

    // Reopen
    rerender(
      <TooltipProvider>
        <DeleteDialog
          open
          onOpenChange={() => {}}
          entityKind="League"
          entityName="X"
          onConfirm={() => {}}
          inputTestId="dd-input"
        />
      </TooltipProvider>,
    );

    expect(screen.getByTestId('dd-input')).toHaveValue('');
  });

  it('disables the input while isLoading', () => {
    setup({ isLoading: true });
    expect(screen.getByTestId('dd-input')).toBeDisabled();
  });

  it('renders the default description fallback when caller omits description', () => {
    setup();
    expect(screen.getByText(/cannot be undone/i)).toBeInTheDocument();
  });

  it('returns null and logs a dev error when entityName is empty', () => {
    // The component uses ~/lib/logger (consola). In dev/test, consola routes
    // log.error to console.error, so spying on console.error captures it.
    const errSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    const { container } = render(
      <TooltipProvider>
        <DeleteDialog
          open
          onOpenChange={() => {}}
          entityKind="League"
          entityName=""
          onConfirm={() => {}}
        />
      </TooltipProvider>,
    );
    expect(container).toBeEmptyDOMElement();
    // Loose match — consola prefixes with the tag name, but the message must appear.
    expect(errSpy).toHaveBeenCalled();
    expect(errSpy.mock.calls.flat().join(' ')).toMatch(/entityName must be non-empty/);
    errSpy.mockRestore();
  });

  it('uses destructive content styling (inherits ConfirmDialog variant)', () => {
    setup();
    expect(screen.getByTestId('dd-content').className).toMatch(/bg-red-950/);
  });

  it('calls onConfirm when name matches and confirm is clicked', async () => {
    const { onConfirm } = setup({ entityName: 'Acme League' });
    fireEvent.change(screen.getByTestId('dd-input'), { target: { value: 'Acme League' } });
    fireEvent.click(screen.getByTestId('dd-confirm'));
    await vi.waitFor(() => expect(onConfirm).toHaveBeenCalledTimes(1));
  });
});
