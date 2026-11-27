import { describe, expect, expectTypeOf, it } from 'vitest';
import type {
  ActionRowChild,
  ContainerChild,
  SectionAccessory,
  TopLevelComponent,
} from '~/components/discord/types';
import {
  DiscordMessageSchema,
  DiscordPreviewRequestSchema,
  type PreviewContext,
  type PreviewContextType,
} from '~/features/event-discord-preview/schemas';

type IsAny<T> = 0 extends 1 & T ? true : false;

describe('event-discord-preview generated types', () => {
  it('keeps discriminated unions typed', () => {
    expectTypeOf<PreviewContextType>().toEqualTypeOf<
      | 'event'
      | 'new_event'
      | 'series_one_off'
      | 'repeater'
      | 'new_repeater'
      | 'org_defaults'
    >();
    expectTypeOf<IsAny<PreviewContext>>().toEqualTypeOf<false>();
    expectTypeOf<IsAny<TopLevelComponent>>().toEqualTypeOf<false>();
    expectTypeOf<IsAny<ContainerChild>>().toEqualTypeOf<false>();
    expectTypeOf<IsAny<ActionRowChild>>().toEqualTypeOf<false>();
    expectTypeOf<IsAny<SectionAccessory>>().toEqualTypeOf<false>();
    expectTypeOf<TopLevelComponent['type']>().toEqualTypeOf<
      1 | 9 | 10 | 12 | 14 | 17
    >();
    expectTypeOf<ActionRowChild['type']>().toEqualTypeOf<
      2 | 3 | 5 | 6 | 7 | 8
    >();

    // @ts-expect-error not a context type
    const badType: PreviewContextType = 'nonsense';
    // @ts-expect-error not a component
    const badComponent: TopLevelComponent = { nonsense: true };
    expect([badType, badComponent]).toHaveLength(2);
  });

  it('rejects a context or component with an unknown tag', () => {
    expect(
      DiscordPreviewRequestSchema.shape.context.safeParse({ type: 'nope' })
        .success,
    ).toBe(false);
    expect(
      DiscordMessageSchema.shape.components.safeParse([{ type: 99 }]).success,
    ).toBe(false);
  });
});
