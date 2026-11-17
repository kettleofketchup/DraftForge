// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { TooltipProvider } from '~/components/ui/tooltip';
import { FormDialog, type FormDialogSize } from '../FormDialog';

// Radix ScrollArea needs ResizeObserver, which jsdom lacks.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??=
  ResizeObserverStub as unknown as typeof ResizeObserver;

function renderDialog(size: FormDialogSize) {
  render(
    <TooltipProvider>
      <FormDialog
        open
        onOpenChange={() => {}}
        title="Sized"
        onSubmit={() => {}}
        size={size}
        data-testid="sized-dialog"
      >
        <div>body</div>
      </FormDialog>
    </TooltipProvider>,
  );
  const content = screen.getByTestId('sized-dialog');
  const scrollArea = content.querySelector('[data-slot="scroll-area"]');
  if (!scrollArea) throw new Error('scroll area missing');
  return { content, scrollArea };
}

describe('FormDialog size', () => {
  it("'screen' fills the height and lets the ScrollArea flex", () => {
    const { content, scrollArea } = renderDialog('screen');
    expect(content).toHaveClass(
      'flex',
      'flex-col',
      'overflow-hidden',
      'min-w-full',
      'sm:h-[95vh]',
    );
    expect(content).not.toHaveClass('sm:h-auto');
    expect(scrollArea).toHaveClass('flex-1', 'min-h-0', '-mx-6', 'px-6');
    expect(scrollArea).not.toHaveClass('sm:max-h-[60vh]');
  });

  it("'lg' keeps the capped ScrollArea", () => {
    const { content, scrollArea } = renderDialog('lg');
    expect(content).toHaveClass('sm:h-auto', 'sm:max-w-lg', 'md:max-w-2xl');
    expect(content).not.toHaveClass('overflow-hidden', 'min-w-full');
    expect(scrollArea).toHaveClass(
      'max-h-[calc(100svh-10rem)]',
      'sm:max-h-[60vh]',
      'pr-4',
    );
    expect(scrollArea).not.toHaveClass('flex-1');
  });
});
