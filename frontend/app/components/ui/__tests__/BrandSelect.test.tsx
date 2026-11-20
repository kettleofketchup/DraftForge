// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import { beforeAll, describe, expect, it } from 'vitest';
import {
  BrandSelect,
  BrandSelectContent,
  BrandSelectItem,
  BrandSelectTrigger,
  SelectValue,
} from '../brand-select';

beforeAll(() => {
  Element.prototype.hasPointerCapture ??= () => false;
  Element.prototype.releasePointerCapture ??= () => undefined;
  Element.prototype.scrollIntoView ??= () => undefined;
});

function renderSelect() {
  render(
    <BrandSelect value="ghost" defaultOpen>
      <BrandSelectTrigger data-testid="trigger">
        <SelectValue />
      </BrandSelectTrigger>
      <BrandSelectContent>
        <BrandSelectItem value="ghost" data-testid="item">
          <svg data-testid="icon" />
          <span>Alice (not a member)</span>
        </BrandSelectItem>
      </BrandSelectContent>
    </BrandSelect>,
  );
}

describe('BrandSelect', () => {
  it('lays the trigger value out as a row so icons stay inline', () => {
    renderSelect();
    const trigger = screen.getByTestId('trigger');
    expect(trigger.className).toContain('*:data-[slot=select-value]:flex');
    expect(trigger.className).toContain(
      '*:data-[slot=select-value]:items-center',
    );
    expect(trigger.className).toContain('*:data-[slot=select-value]:gap-2');
    const value = trigger.querySelector('[data-slot=select-value]')!;
    expect(value.querySelector('svg')).not.toBeNull();
    expect(value.textContent).toBe('Alice (not a member)');
  });

  it('lays item text out as a row so icons stay inline', () => {
    renderSelect();
    const item = screen.getByTestId('item');
    expect(item.className).toContain('*:[span]:last:flex');
    expect(item.className).toContain('*:[span]:last:items-center');
    expect(item.className).toContain('*:[span]:last:gap-2');
  });
});
