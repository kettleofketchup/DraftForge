// @vitest-environment jsdom
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { TooltipProvider } from '~/components/ui/tooltip';
import { DestructiveButton } from '../DestructiveButton';
import { WarningButton } from '../WarningButton';
import { PrimaryButton } from '../PrimaryButton';
import { SecondaryButton } from '../SecondaryButton';

// DestructiveButton/WarningButton hardcoded min-h-11 (the 44px dialog-footer
// touch target), which overrode an explicit size="sm" and left them taller than
// the Primary/Secondary buttons beside them in compact action rows — e.g. the
// series page header, where Delete towered over Edit and Reactivate.

function Wrapper({ children }: { children: React.ReactNode }) {
  return <TooltipProvider>{children}</TooltipProvider>;
}

describe('button size parity', () => {
  it('drops the 44px floor when size="sm" is explicit', () => {
    render(
      <Wrapper>
        <DestructiveButton size="sm">Delete</DestructiveButton>
        <WarningButton size="sm">Warn</WarningButton>
      </Wrapper>,
    );
    expect(screen.getByRole('button', { name: 'Delete' }).className).not.toContain('min-h-11');
    expect(screen.getByRole('button', { name: 'Warn' }).className).not.toContain('min-h-11');
  });

  it('applies the h-8 sm height, matching Primary/Secondary siblings', () => {
    render(
      <Wrapper>
        <DestructiveButton size="sm">Delete</DestructiveButton>
        <PrimaryButton size="sm">Primary</PrimaryButton>
        <SecondaryButton size="sm">Secondary</SecondaryButton>
      </Wrapper>,
    );
    for (const name of ['Delete', 'Primary', 'Secondary']) {
      expect(screen.getByRole('button', { name }).className).toContain('h-8');
    }
  });

  it('keeps the 44px touch target at the default size', () => {
    render(
      <Wrapper>
        <DestructiveButton>Delete</DestructiveButton>
        <WarningButton>Warn</WarningButton>
      </Wrapper>,
    );
    expect(screen.getByRole('button', { name: 'Delete' }).className).toContain('min-h-11');
    expect(screen.getByRole('button', { name: 'Warn' }).className).toContain('min-h-11');
  });
});
