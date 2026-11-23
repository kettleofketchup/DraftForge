// @vitest-environment jsdom
import { fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { describe, expect, it } from 'vitest';
import { IntegerInput } from '../IntegerInput';

function Harness({
  initial,
  min,
  nullable,
}: {
  initial: number | null;
  min?: number;
  nullable?: boolean;
}) {
  const [value, setValue] = useState<number | null>(initial);
  return (
    <>
      <IntegerInput
        data-testid="n"
        value={value}
        onValueChange={setValue}
        min={min}
        nullable={nullable}
      />
      <output data-testid="value">{String(value)}</output>
    </>
  );
}

const input = () => screen.getByTestId('n') as HTMLInputElement;
const committed = () => screen.getByTestId('value').textContent;
const type = (v: string) => fireEvent.change(input(), { target: { value: v } });

describe('IntegerInput', () => {
  it('keeps an empty box while editing instead of snapping', () => {
    render(<Harness initial={20} min={2} />);
    type('');
    expect(input().value).toBe('');
    expect(committed()).toBe('20');
    type('1');
    expect(input().value).toBe('1');
    expect(committed()).toBe('20');
    type('16');
    expect(committed()).toBe('16');
  });

  it('reverts an empty box on blur when not nullable', () => {
    render(<Harness initial={20} min={2} />);
    type('');
    fireEvent.blur(input());
    expect(input().value).toBe('20');
    expect(committed()).toBe('20');
  });

  it('clamps to min on blur', () => {
    render(<Harness initial={20} min={2} />);
    type('1');
    fireEvent.blur(input());
    expect(input().value).toBe('2');
    expect(committed()).toBe('2');
  });

  it('commits null for an empty nullable box', () => {
    render(<Harness initial={20} min={1} nullable />);
    type('');
    expect(committed()).toBe('null');
    fireEvent.blur(input());
    expect(input().value).toBe('');
    expect(committed()).toBe('null');
  });

  it('follows outside value changes', () => {
    function Outside() {
      const [value, setValue] = useState<number | null>(5);
      return (
        <>
          <IntegerInput
            data-testid="n"
            value={value}
            onValueChange={setValue}
          />
          <button onClick={() => setValue(9)}>set</button>
        </>
      );
    }
    render(<Outside />);
    fireEvent.click(screen.getByText('set'));
    expect(input().value).toBe('9');
  });
});
