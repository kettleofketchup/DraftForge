import { describe, expect, expectTypeOf, it } from 'vitest';
import type { DiscordMessage } from '~/features/event-discord-preview/schemas';
import { normalizeMessage, type DiscordMessageInput } from '../messageInput';

describe('DiscordMessageInput', () => {
  it('accepts the generated DiscordMessage and a content-only message', () => {
    expectTypeOf<DiscordMessage>().toExtend<DiscordMessageInput>();
    expectTypeOf<{ content: 'x' }>().toExtend<DiscordMessageInput>();
    const contentOnly: DiscordMessageInput = { content: 'x' };
    expect(contentOnly.content).toBe('x');
  });

  it('normalizeMessage fills missing fields', () => {
    expect(normalizeMessage({ content: 'x' })).toEqual({
      content: 'x',
      embeds: [],
      components: [],
      flags: null,
    });
    expect(normalizeMessage({})).toEqual({
      content: null,
      embeds: [],
      components: [],
      flags: null,
    });
  });
});
