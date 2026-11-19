import { describe, expect, it } from 'vitest';
import { rollCallLabel } from '../schemas';

describe('rollCallLabel', () => {
  it('shows Disabled when roll call is off', () => {
    expect(rollCallLabel(false, 'manual')).toBe('Disabled');
  });

  it('shows Staff-verified for manual mode', () => {
    expect(rollCallLabel(true, 'manual')).toBe('Staff-verified');
  });

  it('shows Automatic for automatic mode', () => {
    expect(rollCallLabel(true, 'automatic')).toBe('Automatic');
  });

  it('falls back to the raw value for an unknown mode', () => {
    expect(rollCallLabel(true, 'future_mode')).toBe('future_mode');
  });
});
