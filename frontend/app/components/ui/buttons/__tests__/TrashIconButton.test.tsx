// @vitest-environment jsdom
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { TooltipProvider } from '~/components/ui/tooltip';
import { TrashIconButton } from '../icons/TrashIconButton';

describe('TrashIconButton', () => {
  it('does not submit an enclosing form', () => {
    const onSubmit = vi.fn((e: React.FormEvent) => e.preventDefault());
    const onClick = vi.fn();
    render(
      <TooltipProvider>
        <form onSubmit={onSubmit}>
          <TrashIconButton tooltip="Delete league" onClick={onClick} />
        </form>
      </TooltipProvider>,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Delete league' }));

    expect(onClick).toHaveBeenCalledOnce();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('still allows an explicit submit type', () => {
    const onSubmit = vi.fn((e: React.FormEvent) => e.preventDefault());
    render(
      <TooltipProvider>
        <form onSubmit={onSubmit}>
          <TrashIconButton type="submit" />
        </form>
      </TooltipProvider>,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Delete' }));

    expect(onSubmit).toHaveBeenCalledOnce();
  });
});
