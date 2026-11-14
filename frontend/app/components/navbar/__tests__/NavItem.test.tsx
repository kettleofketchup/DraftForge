// @vitest-environment jsdom
import { fireEvent, render, screen } from '@testing-library/react';
import * as React from 'react';
import { MemoryRouter } from 'react-router';
import { describe, expect, it, vi } from 'vitest';
import { TooltipProvider } from '~/components/ui/tooltip';
import { DocsIcon } from '../icons';
import { NavItem } from '../NavItem';

function renderInShell(ui: React.ReactElement) {
  return render(
    <TooltipProvider>
      <MemoryRouter>{ui}</MemoryRouter>
    </TooltipProvider>,
  );
}

describe('NavItem', () => {
  it('renders a typed Button for as="button"', () => {
    const spy = vi.fn();
    const ref = React.createRef<HTMLElement>();
    renderInShell(
      <NavItem
        as="button"
        ref={ref}
        title="Docs"
        aria-label="Documentation"
        data-testid="nav-docs-trigger"
        aria-expanded={false}
        onClick={spy}
        icon={<DocsIcon />}
        badge={<span data-testid="badge" />}
      />,
    );

    const trigger = screen.getByTestId('nav-docs-trigger');
    expect(trigger.tagName).toBe('BUTTON');
    expect(trigger.getAttribute('type')).toBe('button');
    expect(trigger.getAttribute('aria-label')).toBe('Documentation');
    expect(trigger.getAttribute('aria-expanded')).toBe('false');
    expect(trigger.querySelector('svg')?.getAttribute('class')).toContain(
      'size-5',
    );
    expect(trigger.contains(screen.getByTestId('badge'))).toBe(true);
    expect(trigger.textContent).toContain('Docs');
    expect(trigger.className).toContain('px-1.5');
    expect(trigger.className).not.toContain('px-4');
    expect(trigger.className).not.toContain('px-3');

    fireEvent.click(trigger);
    expect(spy).toHaveBeenCalledTimes(1);
    expect(ref.current).toBe(trigger);
  });

  it('still renders a router link for to=', () => {
    renderInShell(<NavItem to="/about" title="About" />);
    expect(screen.getByTestId('nav-link-about').tagName).toBe('A');
  });
});
