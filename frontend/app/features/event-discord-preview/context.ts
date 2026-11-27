import type { PreviewContext } from './schemas';

export type DiscordPreviewContext =
  | { type: 'event'; eventId: number }
  | { type: 'new_event'; organizationId: number }
  | { type: 'series_one_off'; repeaterId: number }
  | { type: 'repeater'; repeaterId: number }
  | { type: 'new_repeater'; organizationId: number };

export type PreviewValuesMode = 'event' | 'repeater';

export function toApiContext(context: DiscordPreviewContext): PreviewContext {
  switch (context.type) {
    case 'event':
      return { type: 'event', event_id: context.eventId };
    case 'new_event':
      return { type: 'new_event', organization_id: context.organizationId };
    case 'series_one_off':
      return { type: 'series_one_off', repeater_id: context.repeaterId };
    case 'repeater':
      return { type: 'repeater', repeater_id: context.repeaterId };
    case 'new_repeater':
      return { type: 'new_repeater', organization_id: context.organizationId };
  }
}

export function valuesModeFor(context: DiscordPreviewContext): {
  mode: PreviewValuesMode;
  creating: boolean;
} {
  return {
    mode:
      context.type === 'repeater' || context.type === 'new_repeater'
        ? 'repeater'
        : 'event',
    creating: context.type === 'new_repeater',
  };
}
