import { describe, expect, it } from 'vitest';
import { ChatErrorCodeSchema } from '../../schemas';
import { chatErrorText } from '../chatErrors';

describe('chatErrorText', () => {
  it.each(ChatErrorCodeSchema.options)('has human text for %s', (code) => {
    const text = chatErrorText(code);
    expect(text.length).toBeGreaterThan(0);
    expect(text).not.toContain('_');
  });

  it('uses the spec wording for rate limits and spectators', () => {
    expect(chatErrorText('rate_limited')).toBe('Slow down a moment');
    expect(chatErrorText('not_participant')).toBe(
      'Spectators can only read chat',
    );
  });
});
