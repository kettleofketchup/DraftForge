// @vitest-environment jsdom
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { RadioGroup, RadioGroupItem } from '../radio-group';

const RAW_PALETTE =
  /\b(?:bg|text|border|ring|from|via|to|shadow|fill|stroke|outline)-(?:slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)-\d/;
const RAW_HEX = /#[0-9a-f]{3,8}\b/i;

function renderGroup(
  props: { defaultValue?: string; disabledValue?: string } = {},
) {
  render(
    <RadioGroup defaultValue={props.defaultValue} aria-label="Scope">
      <RadioGroupItem
        value="future"
        aria-label="Future"
        disabled={props.disabledValue === 'future'}
      />
      <RadioGroupItem
        value="past"
        aria-label="Past"
        disabled={props.disabledValue === 'past'}
      />
    </RadioGroup>,
  );
}

function allClasses(el: Element): string {
  return [el, ...el.querySelectorAll('*')]
    .map((node) => node.getAttribute('class') ?? '')
    .join(' ');
}

describe('RadioGroupItem', () => {
  it('resets the global button padding and keeps its 16px size', () => {
    renderGroup();
    const item = screen.getByRole('radio', { name: 'Future' });
    expect(item).toHaveClass('p-0', 'shrink-0', 'h-4', 'w-4', 'rounded-full');
  });

  it('neutralises the base-layer hover border and focus outline', () => {
    renderGroup();
    const item = screen.getByRole('radio', { name: 'Future' });
    expect(item).toHaveClass('outline-none', 'enabled:hover:border-primary');
  });

  it('uses brand tokens and no raw palette or hex colours', () => {
    renderGroup({ defaultValue: 'future' });
    const item = screen.getByRole('radio', { name: 'Future' });
    const classes = allClasses(item);
    expect(classes).not.toMatch(RAW_PALETTE);
    expect(classes).not.toMatch(RAW_HEX);
    expect(item).toHaveClass(
      'border-primary/60',
      'focus-visible:ring-ring',
      'enabled:data-[state=checked]:shadow-[0_0_10px_var(--glow-violet)]',
    );
  });

  it('renders the brand gradient dot only when checked', () => {
    renderGroup({ defaultValue: 'future' });
    const checked = screen.getByRole('radio', { name: 'Future' });
    const unchecked = screen.getByRole('radio', { name: 'Past' });

    expect(checked).toHaveAttribute('data-state', 'checked');
    const dot = checked.querySelector('[data-slot="radio-group-dot"]');
    expect(dot).not.toBeNull();
    expect(dot).toHaveClass('from-primary', 'to-interactive');
    expect(unchecked.querySelector('[data-slot="radio-group-dot"]')).toBeNull();

    fireEvent.click(unchecked);
    expect(unchecked).toHaveAttribute('data-state', 'checked');
    expect(
      unchecked.querySelector('[data-slot="radio-group-dot"]'),
    ).not.toBeNull();
  });

  it('disables an item and leaves it unselectable', () => {
    renderGroup({ defaultValue: 'future', disabledValue: 'past' });
    const disabled = screen.getByRole('radio', { name: 'Past' });
    expect(disabled).toBeDisabled();
    expect(disabled).toHaveClass('disabled:opacity-50', 'disabled:shadow-none');

    fireEvent.click(disabled);
    expect(disabled).toHaveAttribute('data-state', 'unchecked');
  });

  it('merges a caller className such as sr-only', () => {
    render(
      <RadioGroup aria-label="Rank">
        <RadioGroupItem
          value="active"
          aria-label="Active"
          className="sr-only"
        />
      </RadioGroup>,
    );
    expect(screen.getByRole('radio', { name: 'Active' })).toHaveClass(
      'sr-only',
    );
  });
});
