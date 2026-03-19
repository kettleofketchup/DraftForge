import type { Control, UseFormWatch } from 'react-hook-form';
import {
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '~/components/ui/form';
import { Input } from '~/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '~/components/ui/select';
import { Textarea } from '~/components/ui/textarea';
import { DiscordChannelPicker } from './DiscordChannelPicker';
import { DiscordRolePicker } from './DiscordRolePicker';

const REMINDER_HOURS_OPTIONS = [
  { value: 1, label: '1 hour before' },
  { value: 2, label: '2 hours before' },
  { value: 4, label: '4 hours before' },
  { value: 6, label: '6 hours before' },
  { value: 12, label: '12 hours before' },
  { value: 24, label: '1 day before' },
  { value: 48, label: '2 days before' },
];

export const DiscordIcon = ({ className }: { className?: string }) => (
  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className={className}>
    <path d="M20.317 4.3698a19.7913 19.7913 0 00-4.8851-1.5152.0741.0741 0 00-.0785.0371c-.211.3753-.4447.8648-.6083 1.2495-1.8447-.2762-3.68-.2762-5.4868 0-.1636-.3933-.4058-.8742-.6177-1.2495a.077.077 0 00-.0785-.037 19.7363 19.7363 0 00-4.8852 1.515.0699.0699 0 00-.0321.0277C.5334 9.0458-.319 13.5799.0992 18.0578a.0824.0824 0 00.0312.0561c2.0528 1.5076 4.0413 2.4228 5.9929 3.0294a.0777.0777 0 00.0842-.0276c.4616-.6304.8731-1.2952 1.226-1.9942a.076.076 0 00-.0416-.1057c-.6528-.2476-1.2743-.5495-1.8722-.8923a.077.077 0 01-.0076-.1277c.1258-.0943.2517-.1923.3718-.2914a.0743.0743 0 01.0776-.0105c3.9278 1.7933 8.18 1.7933 12.0614 0a.0739.0739 0 01.0785.0095c.1202.099.246.1981.3728.2924a.077.077 0 01-.0066.1276 12.2986 12.2986 0 01-1.873.8914.0766.0766 0 00-.0407.1067c.3604.698.7719 1.3628 1.225 1.9932a.076.076 0 00.0842.0286c1.961-.6067 3.9495-1.5219 6.0023-3.0294a.077.077 0 00.0313-.0552c.5004-5.177-.8382-9.6739-3.5485-13.6604a.061.061 0 00-.0312-.0286zM8.02 15.3312c-1.1825 0-2.1569-1.0857-2.1569-2.419 0-1.3332.9555-2.4189 2.157-2.4189 1.2108 0 2.1757 1.0952 2.1568 2.419 0 1.3332-.9555 2.4189-2.1569 2.4189zm7.9748 0c-1.1825 0-2.1569-1.0857-2.1569-2.419 0-1.3332.9554-2.4189 2.1569-2.4189 1.2108 0 2.1757 1.0952 2.1568 2.419 0 1.3332-.946 2.4189-2.1568 2.4189Z" />
  </svg>
);

/** Reusable checkbox field for Discord config options */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function CheckboxField({ control, name, label, description }: {
  control: Control<any>;
  name: string;
  label: string;
  description: string;
}) {
  return (
    <FormField
      control={control}
      name={name}
      render={({ field }) => (
        <FormItem className="flex items-center gap-3">
          <FormControl>
            <input
              type="checkbox"
              data-testid={`discord-${name}`}
              checked={field.value}
              onChange={field.onChange}
              className="h-4 w-4 rounded border-border accent-primary"
            />
          </FormControl>
          <div>
            <FormLabel className="text-sm font-medium cursor-pointer">{label}</FormLabel>
            <FormDescription>{description}</FormDescription>
          </div>
        </FormItem>
      )}
    />
  );
}

/** Reusable hours dropdown for reminder timing */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function HoursSelect({ control, name, label }: {
  control: Control<any>;
  name: string;
  label?: string;
}) {
  return (
    <div className="ml-7">
      <FormField
        control={control}
        name={name}
        render={({ field }) => (
          <FormItem>
            <FormLabel>{label ?? 'When to send'}</FormLabel>
            <Select
              onValueChange={(val) => field.onChange(parseInt(val, 10))}
              value={field.value?.toString()}
            >
              <FormControl>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
              </FormControl>
              <SelectContent>
                {REMINDER_HOURS_OPTIONS.map((opt) => (
                  <SelectItem key={opt.value} value={String(opt.value)}>
                    {opt.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <FormMessage />
          </FormItem>
        )}
      />
    </div>
  );
}

interface DiscordConfigSectionProps {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  control: Control<any>;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  watch: UseFormWatch<any>;
  isRepeater: boolean;
  organizationId: number;
}

export function DiscordConfigSection({ control, watch, isRepeater, organizationId }: DiscordConfigSectionProps) {
  const [createEvent, signupReminder, profileReminder, confirmAttendance, postSignups, announcement] = watch([
    'discord_create_event',
    'discord_signup_reminder',
    'discord_profile_reminder',
    'discord_confirm_attendance',
    'discord_post_signups',
    'discord_announcement',
  ]);

  return (
    <div className="space-y-3">
      {/* Create Discord event */}
      <div className="rounded-md border border-border p-3 space-y-3">
        <CheckboxField control={control} name="discord_create_event"
          label="Create Discord scheduled event"
          description="Automatically creates a scheduled event in your Discord server"
        />
        {createEvent && (
          <div className="space-y-3 ml-7">
            <CheckboxField control={control} name="discord_sync_signups"
              label="Synchronize signups"
              description="Keep website and Discord event signups in sync"
            />
            <CheckboxField control={control} name="discord_mark_interested"
              label="Mark signups as interested"
              description="Players who sign up will be marked as interested on the Discord event"
            />
            <FormField control={control} name="discord_event_title"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Event title</FormLabel>
                  <FormControl>
                    <Input placeholder="Leave blank to use event name" {...field} />
                  </FormControl>
                  <FormDescription>Custom title for the Discord event. If blank, the event name is used.</FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField control={control} name="discord_event_description"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Event description</FormLabel>
                  <FormControl>
                    <Textarea placeholder="Discord event description" rows={2} {...field} />
                  </FormControl>
                  <FormDescription>Shown as the main description of the Discord scheduled event</FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField control={control} name="discord_event_info"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Additional info</FormLabel>
                  <FormControl>
                    <Textarea placeholder="Extra details, rules, links..." rows={2} {...field} />
                  </FormControl>
                  <FormDescription>Extra information appended to the Discord event details</FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />
          </div>
        )}
      </div>

      {/* Signup reminder */}
      <div className="rounded-md border border-border p-3 space-y-3">
        <CheckboxField control={control} name="discord_signup_reminder"
          label="Send signup reminder"
          description="DM users who haven't signed up yet before the event starts"
        />
        {signupReminder && (
          <HoursSelect control={control} name="discord_signup_reminder_hours" label="Hours before event" />
        )}
      </div>

      {/* Profile reminder */}
      <div className="rounded-md border border-border p-3 space-y-3">
        <CheckboxField control={control} name="discord_profile_reminder"
          label="Profile update reminder"
          description="DM signed-up users to complete their profile (Steam ID, MMR) before the event"
        />
        {profileReminder && (
          <HoursSelect control={control} name="discord_profile_reminder_hours" />
        )}
      </div>

      {/* Confirm attendance */}
      <div className="rounded-md border border-border p-3 space-y-3">
        <CheckboxField control={control} name="discord_confirm_attendance"
          label="Confirm attendance via Discord"
          description="Require players to reply to a Discord message on event day to confirm they'll attend"
        />
        {confirmAttendance && (
          <HoursSelect control={control} name="discord_confirm_attendance_hours" />
        )}
      </div>

      {/* Post event signup embed */}
      <div className="rounded-md border border-border p-3 space-y-3">
        <CheckboxField control={control} name="discord_post_signups"
          label="Post event signup embed"
          description="Post an embed to a channel where users can react to sign up"
        />
        {postSignups && (
          <div className="ml-7 space-y-3">
            <FormField control={control} name="discord_post_signups_channel_id"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Signup channel</FormLabel>
                  <FormControl>
                    <DiscordChannelPicker organizationId={organizationId} value={field.value} onChange={field.onChange} data-testid="discord-signup-channel-select" />
                  </FormControl>
                  <FormDescription>Channel where the signup embed will be posted</FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField control={control} name="discord_signup_role_ids"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Mention roles in signup post</FormLabel>
                  <FormControl>
                    <DiscordRolePicker
                      organizationId={organizationId}
                      value={field.value || []}
                      onChange={field.onChange}
                    />
                  </FormControl>
                  <FormDescription>Discord role IDs to @mention in the signup post</FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />
          </div>
        )}
      </div>

      {/* Pre-day announcement */}
      <div className="rounded-md border border-border p-3 space-y-3">
        <CheckboxField control={control} name="discord_announcement"
          label="Pre-day announcement"
          description="Post an announcement in a channel before the event"
        />
        {announcement && (
          <div className="ml-7 space-y-3">
            <FormField control={control} name="discord_announcement_channel_id"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Announcement channel</FormLabel>
                  <FormControl>
                    <DiscordChannelPicker organizationId={organizationId} value={field.value} onChange={field.onChange} />
                  </FormControl>
                  <FormDescription>Channel where the announcement will be posted</FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField control={control} name="discord_announcement_hours"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Hours before event</FormLabel>
                  <FormControl>
                    <Input type="number" min={1} {...field}
                      onChange={(e) => field.onChange(parseInt(e.target.value, 10) || 24)} />
                  </FormControl>
                  <FormDescription>How many hours before the event to post the announcement</FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField control={control} name="discord_announcement_role_ids"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Mention roles in announcement</FormLabel>
                  <FormControl>
                    <DiscordRolePicker
                      organizationId={organizationId}
                      value={field.value || []}
                      onChange={field.onChange}
                    />
                  </FormControl>
                  <FormDescription>Discord role IDs to @mention when announcement is posted</FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />
          </div>
        )}
      </div>

      {/* Notify new events — repeater only */}
      {isRepeater && (
        <div className="rounded-md border border-border p-3">
          <CheckboxField control={control} name="discord_notify_new_events"
            label="Message interested users"
            description="DM subscribed users when new events are created or cancelled"
          />
        </div>
      )}
    </div>
  );
}
