// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { Tabs, TabsList, TabsTrigger } from '../tabs';

function renderTabs() {
  render(
    <Tabs defaultValue="details">
      <TabsList>
        <TabsTrigger value="details">Details</TabsTrigger>
        <TabsTrigger value="signups">Signups</TabsTrigger>
      </TabsList>
    </Tabs>,
  );
  return {
    active: screen.getByRole('tab', { name: 'Details' }),
    inactive: screen.getByRole('tab', { name: 'Signups' }),
  };
}

describe('TabsTrigger', () => {
  it('styles both states with brand tokens, not raw palette colours', () => {
    const { active, inactive } = renderTabs();
    for (const tab of [active, inactive]) {
      expect(tab.className).not.toMatch(/\b(violet|blue|indigo|purple)-\d/);
    }
    expect(inactive.className).toContain('data-[state=inactive]:border-border');
    expect(inactive.className).toContain('data-[state=inactive]:bg-primary/15');
    expect(active.className).toContain(
      'data-[state=active]:[background-image:var(--brand-gradient)]',
    );
  });

  it('gives every state the same transparent-by-default border and no base-button outline', () => {
    const { active } = renderTabs();
    expect(active).toHaveAttribute('data-state', 'active');
    expect(active.className).toMatch(/(^|\s)border(\s|$)/);
    expect(active.className).toContain('border-transparent');
    expect(active.className).toContain('outline-none');
    expect(active.className).toContain('focus-visible:ring-offset-background');
  });
});
