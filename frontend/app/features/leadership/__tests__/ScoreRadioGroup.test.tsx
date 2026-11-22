// @vitest-environment jsdom
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ScoreRadioGroup } from '../ScoreRadioGroup';

function renderGroup(
  props: Partial<Parameters<typeof ScoreRadioGroup>[0]> = {},
) {
  const onChange = vi.fn();
  render(
    <ScoreRadioGroup
      name="drafting"
      label="Drafting"
      value={3}
      onChange={onChange}
      testIdPrefix="leadership-review-drafting"
      {...props}
    />,
  );
  return onChange;
}

describe('ScoreRadioGroup', () => {
  it('is a labelled radio group operable by keyboard', async () => {
    const onChange = renderGroup();
    const group = screen.getByRole('radiogroup', { name: 'Drafting' });
    expect(group).toBeInTheDocument();
    const three = screen.getByRole('radio', { name: '3' });
    expect(three).toHaveAttribute('aria-checked', 'true');

    act(() => three.focus());
    fireEvent.keyDown(three, { key: 'ArrowRight' });

    await waitFor(() => expect(onChange).toHaveBeenCalledWith(4));
    expect(screen.getByRole('radio', { name: '4' })).toHaveFocus();
  });

  it('selects a score on click', () => {
    const onChange = renderGroup({ value: undefined });
    fireEvent.click(screen.getByRole('radio', { name: '5' }));
    expect(onChange).toHaveBeenCalledWith(5);
  });

  it('has 44px touch targets', () => {
    renderGroup();
    for (const n of [1, 2, 3, 4, 5]) {
      expect(screen.getByTestId(`leadership-review-drafting-${n}`)).toHaveClass(
        'min-h-11',
      );
    }
  });

  it('can be disabled', () => {
    const onChange = renderGroup({ disabled: true });
    const five = screen.getByRole('radio', { name: '5' });
    expect(five).toBeDisabled();
    fireEvent.click(five);
    expect(onChange).not.toHaveBeenCalled();
  });
});
