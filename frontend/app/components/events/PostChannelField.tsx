import { TriangleAlert } from 'lucide-react';
import type { Control } from 'react-hook-form';
import { Alert, AlertDescription } from '~/components/ui/alert';
import {
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '~/components/ui/form';
import { DiscordChannelPicker } from './DiscordChannelPicker';
import type { DiscordFields } from './DiscordConfigSection';
import type { PostChannelState } from './postChannelState';

export type PostChannelFieldName =
  | 'discord_post_signups_channel_id'
  | 'discord_confirm_attendance_channel_id'
  | 'discord_profile_reminder_channel_id'
  | 'discord_new_event_channel_id';

interface PostChannelFieldProps {
  control: Control<DiscordFields>;
  name: PostChannelFieldName;
  label: string;
  description?: string;
  organizationId: number;
  /** Where the post goes when its own channel is blank. */
  blankState: PostChannelState;
  noChannelWarning: string;
  'data-testid': string;
}

export function PostChannelField({
  control,
  name,
  label,
  description,
  organizationId,
  blankState,
  noChannelWarning,
  'data-testid': testId,
}: PostChannelFieldProps) {
  const clearable =
    blankState.kind === 'fallback'
      ? {
          label: 'Use announcement channel',
          fallbackChannelId: blankState.channelId,
        }
      : { label: 'No channel selected' };

  return (
    <FormField
      control={control}
      name={name}
      render={({ field }) => (
        <FormItem>
          <FormLabel>{label}</FormLabel>
          <FormControl>
            <DiscordChannelPicker
              organizationId={organizationId}
              value={field.value ?? ''}
              onChange={field.onChange}
              clearable={clearable}
              data-testid={testId}
            />
          </FormControl>
          {description && <FormDescription>{description}</FormDescription>}
          {!field.value && blankState.kind === 'none' && (
            <Alert
              data-testid={`${testId}-no-channel`}
              className="border-warning/30 bg-warning/10 text-warning [&>svg]:text-warning"
            >
              <TriangleAlert />
              <AlertDescription>{noChannelWarning}</AlertDescription>
            </Alert>
          )}
          <FormMessage />
        </FormItem>
      )}
    />
  );
}
