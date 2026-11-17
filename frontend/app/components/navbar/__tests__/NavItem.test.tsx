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
  it('renders a typed button for as="button"', () => {
    const spy = vi.fn();
    const ref = React.createRef<HTMLElement>();
    renderInShell(
      <NavItem
        as="button"
        ref={ref}
        title="Docs"
        tier="external"
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

  it('styles the button form like the link form', () => {
    renderInShell(
      <>
        <NavItem as="button" title="Docs" tier="external" data-testid="b" />
        <NavItem
          href="https://x.test"
          title="X"
          tier="external"
          data-testid="a"
        />
      </>,
    );
    const button = screen.getByTestId('b');
    expect(button.className).toBe(screen.getByTestId('a').className);
    expect(button.className).not.toMatch(/scale|accent/);
  });

  it('still renders a router link for to=', () => {
    renderInShell(<NavItem to="/about" title="About" tier="main" />);
    expect(screen.getByTestId('nav-link-about').tagName).toBe('A');
  });

  it('names icon-only items by their title unless aria-label is given', () => {
    renderInShell(
      <>
        <NavItem to="/about" title="About" tier="main" />
        <NavItem as="button" title="Docs" tier="external" data-testid="b" />
        <NavItem
          href="https://x.test"
          title="X"
          aria-label="Star X"
          tier="external"
          data-testid="a"
        />
      </>,
    );
    expect(
      screen.getByTestId('nav-link-about').getAttribute('aria-label'),
    ).toBe('About');
    expect(screen.getByTestId('b').getAttribute('aria-label')).toBe('Docs');
    expect(screen.getByTestId('a').getAttribute('aria-label')).toBe('Star X');
  });

  it('collapses labels on the container for main and the viewport for external', () => {
    renderInShell(
      <>
        <NavItem to="/about" title="About" subtitle="Learn more" tier="main" />
        <NavItem
          as="button"
          title="Docs"
          subtitle="Read the docs"
          tier="external"
          data-testid="b"
        />
      </>,
    );
    const mainLabel = screen.getByText('About').parentElement!.parentElement!;
    expect(mainLabel.className).toContain('@min-[700px]:flex');
    expect(screen.getByText('Learn more').className).toContain(
      '@min-[840px]:block',
    );
    const externalLabel =
      screen.getByText('Docs').parentElement!.parentElement!;
    expect(externalLabel.className).toContain('min-[1600px]:flex');
    expect(screen.getByText('Read the docs').className).toContain(
      'min-[1920px]:block',
    );
  });
});
