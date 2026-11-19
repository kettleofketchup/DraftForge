// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import '../../events/__tests__/eventModalFixtures';
import { RadioGroup, RadioGroupItem } from '../radio-group';

describe('RadioGroupItem', () => {
  // app.css gives every base-layer button 0.6em 1.2em padding, which
  // stretches the 16px circle into a pill and hides the checked dot.
  it('resets the global button padding', () => {
    render(
      <RadioGroup defaultValue="a">
        <RadioGroupItem value="a" aria-label="a" />
      </RadioGroup>,
    );
    expect(screen.getByRole('radio', { name: 'a' })).toHaveClass(
      'p-0',
      'shrink-0',
    );
  });
});
