import { TriangleAlert } from 'lucide-react';
import type { ReactNode } from 'react';
import { useWatch, type Control, type FieldValues } from 'react-hook-form';
import type { z } from 'zod';
import { IntegerInput } from '~/components/patterns/IntegerInput';
import { Alert, AlertDescription } from '~/components/ui/alert';
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
import {
  DiscordPermissionBadge,
  RecheckPermissionsButton,
  usePermissionPreview,
  type PermissionCheckResult,
  type PermissionQuery,
  type PermissionScope,
} from '~/features/discord-permissions';
import {
  channelPermissionGroups,
  channelUseLabel,
  SETTING_LABELS,
  SETTINGS_OPERATIONS,
  settingsDescriptors,
  type ChannelPicker,
} from '~/features/discord-permissions/descriptors';
import {
  EventDiscordPreviewButton,
  type DiscordPreviewContext,
  type PreviewKind,
} from '~/features/event-discord-preview';
import { DiscordChannelPicker } from './DiscordChannelPicker';
import { DiscordRolePicker } from './DiscordRolePicker';
import { fallbackChannelUsers } from './fallbackChannelUsers';
import {
  ATTENDANCE_REMINDER_DESCRIPTION,
  EVENT_SECTION_FIELDS,
  NEW_EVENTS_DESCRIPTION,
  PROFILE_REMINDER_DESCRIPTION,
  SIGNUP_REMINDER_LABEL,
} from './form/settingsFields';
import { PostChannelField } from './PostChannelField';
import {
  NO_CHANNEL_WARNING,
  postChannelState,
  SIGNUP_NO_CHANNEL_WARNING,
  type ChannelPost,
} from './postChannelState';
import type { discordConfigSchema } from './schemas';
import {
  START_MENTION_PREREQUISITE_NOTE,
  startMentionPrerequisite,
  startMentionPrerequisiteMessage,
} from './startMentionPrerequisite';

/** Field set covered by this section. Includes discordConfigSchema's input
 *  plus the repeater-only `discord_notify_new_events` flag — that field lives
 *  on createEventInputSchema + editRepeaterSchema directly (not in the shared
 *  sub-schema) because non-repeater forms don't expose it, but the JSX still
 *  references it under the `showNotifyNewEvents` guard. */
export type DiscordFields = z.input<typeof discordConfigSchema> & {
  discord_notify_new_events?: boolean;
};
type DiscordFieldName = Extract<keyof DiscordFields, string>;

const REMINDER_HOURS_OPTIONS = [
  { value: 1, label: '1 hour before' },
  { value: 2, label: '2 hours before' },
  { value: 4, label: '4 hours before' },
  { value: 6, label: '6 hours before' },
  { value: 12, label: '12 hours before' },
  { value: 24, label: '1 day before' },
  { value: 48, label: '2 days before' },
];

const START_MENTION_MINUTES_OPTIONS = [
  { value: 5, label: '5 minutes before' },
  { value: 10, label: '10 minutes before' },
  { value: 15, label: '15 minutes before' },
  { value: 30, label: '30 minutes before' },
  { value: 60, label: '1 hour before' },
];

const START_MENTION_SCOPE_OPTIONS = [
  { value: 'all_active', label: 'All active signups (incl. waitlist)' },
  { value: 'main', label: 'Main list only' },
];

export const DiscordIcon = ({ className }: { className?: string }) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 24 24"
    fill="currentColor"
    className={className}
  >
    <path d="M20.317 4.3698a19.7913 19.7913 0 00-4.8851-1.5152.0741.0741 0 00-.0785.0371c-.211.3753-.4447.8648-.6083 1.2495-1.8447-.2762-3.68-.2762-5.4868 0-.1636-.3933-.4058-.8742-.6177-1.2495a.077.077 0 00-.0785-.037 19.7363 19.7363 0 00-4.8852 1.515.0699.0699 0 00-.0321.0277C.5334 9.0458-.319 13.5799.0992 18.0578a.0824.0824 0 00.0312.0561c2.0528 1.5076 4.0413 2.4228 5.9929 3.0294a.0777.0777 0 00.0842-.0276c.4616-.6304.8731-1.2952 1.226-1.9942a.076.076 0 00-.0416-.1057c-.6528-.2476-1.2743-.5495-1.8722-.8923a.077.077 0 01-.0076-.1277c.1258-.0943.2517-.1923.3718-.2914a.0743.0743 0 01.0776-.0105c3.9278 1.7933 8.18 1.7933 12.0614 0a.0739.0739 0 01.0785.0095c.1202.099.246.1981.3728.2924a.077.077 0 01-.0066.1276 12.2986 12.2986 0 01-1.873.8914.0766.0766 0 00-.0407.1067c.3604.698.7719 1.3628 1.225 1.9932a.076.076 0 00.0842.0286c1.961-.6067 3.9495-1.5219 6.0023-3.0294a.077.077 0 00.0313-.0552c.5004-5.177-.8382-9.6739-3.5485-13.6604a.061.061 0 00-.0312-.0286zM8.02 15.3312c-1.1825 0-2.1569-1.0857-2.1569-2.419 0-1.3332.9555-2.4189 2.157-2.4189 1.2108 0 2.1757 1.0952 2.1568 2.419 0 1.3332-.9555 2.4189-2.1569 2.4189zm7.9748 0c-1.1825 0-2.1569-1.0857-2.1569-2.419 0-1.3332.9554-2.4189 2.1569-2.4189 1.2108 0 2.1757 1.0952 2.1568 2.419 0 1.3332-.946 2.4189-2.1568 2.4189Z" />
  </svg>
);

function CheckboxField({
  control,
  name,
  label,
  description,
  diagnostic,
  action,
}: {
  control: Control<DiscordFields>;
  name: DiscordFieldName;
  label: string;
  description: string;
  diagnostic?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <FormField
      control={control}
      name={name}
      render={({ field }) => (
        <FormItem className="flex items-start gap-3 space-y-0">
          <FormControl>
            <input
              type="checkbox"
              data-testid={`discord-${name}`}
              checked={!!field.value}
              onChange={field.onChange}
              className="mt-0.5 h-4 w-4 shrink-0 rounded border-border accent-primary"
            />
          </FormControl>
          <div className="min-w-0 flex-1">
            <FormLabel className="text-sm font-medium cursor-pointer">
              {label}
            </FormLabel>
            <FormDescription>{description}</FormDescription>
            {diagnostic}
          </div>
          {action ? <div className="shrink-0">{action}</div> : null}
        </FormItem>
      )}
    />
  );
}

function HoursSelect({
  control,
  name,
  label,
  options = REMINDER_HOURS_OPTIONS,
}: {
  control: Control<DiscordFields>;
  name: DiscordFieldName;
  label?: string;
  options?: { value: number; label: string }[];
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
                <SelectTrigger
                  className="w-full"
                  data-testid={`discord-${name}-select`}
                >
                  <SelectValue />
                </SelectTrigger>
              </FormControl>
              <SelectContent>
                {options.map((opt) => (
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

function Subsection({
  testId,
  title,
  children,
}: {
  testId: string;
  title: string;
  children: ReactNode;
}) {
  return (
    <section data-testid={testId} className="space-y-3">
      <h4 className="text-sm font-semibold text-foreground">{title}</h4>
      {children}
    </section>
  );
}

function AnnouncementChannelField({
  control,
  organizationId,
  lead,
  users,
  diagnostic,
}: {
  control: Control<DiscordFields>;
  organizationId: number;
  lead: string;
  users: string[];
  diagnostic?: ReactNode;
}) {
  return (
    <FormField
      control={control}
      name="discord_announcement_channel_id"
      render={({ field }) => (
        <FormItem>
          <FormLabel>Announcement channel</FormLabel>
          <FormControl>
            <DiscordChannelPicker
              organizationId={organizationId}
              value={field.value}
              onChange={field.onChange}
              data-testid="discord-announcement-channel-select"
            />
          </FormControl>
          {diagnostic}
          <FormDescription>
            {lead}
            <span className="block">{`Used by: ${users.join(', ')}`}</span>
          </FormDescription>
          <FormMessage />
        </FormItem>
      )}
    />
  );
}

const discordLabel = (field: string): string =>
  EVENT_SECTION_FIELDS.discord[field].label;

const signupReminderMeta = EVENT_SECTION_FIELDS.discord.discord_signup_reminder;

const SUBSCRIBE_NOTE =
  "Members subscribe on the series page, or with Notify Me on the event's signup post in Discord.";

export interface DiscordConfigSectionProps<
  T extends FieldValues & DiscordFields,
> {
  control: Control<T>;
  permissionScope?: PermissionScope | null;
  canCheckPermissions?: boolean;
  isRepeater: boolean;
  organizationId: number;
  /** Gates the repeater-only "Post new events" block. Defaults to
   *  `isRepeater`; a one-off event inherits the series' setting instead of
   *  exposing its own toggle. */
  showNotifyNewEvents?: boolean;
  /** What the Preview buttons build from; absent for org defaults. */
  previewContext?: DiscordPreviewContext;
  /** Shows the signup-reminder DM. Defaults to `isRepeater`; org defaults
   *  pass it to edit the value new series inherit. */
  showSignupReminder?: boolean;
}

export function DiscordConfigSection<T extends FieldValues & DiscordFields>(
  props: DiscordConfigSectionProps<T>,
) {
  return props.canCheckPermissions && props.permissionScope ? (
    <CheckedDiscordConfigSection {...props} scope={props.permissionScope} />
  ) : (
    <DiscordConfigFields {...props} />
  );
}

function CheckedDiscordConfigSection<T extends FieldValues & DiscordFields>(
  props: DiscordConfigSectionProps<T> & { scope: PermissionScope },
) {
  const values = useWatch({ control: props.control }) as DiscordFields;
  const descriptors = settingsDescriptors(values, {
    isRepeater: props.isRepeater,
    showNotifyNewEvents: props.showNotifyNewEvents ?? props.isRepeater,
    showSignupReminder: props.showSignupReminder ?? props.isRepeater,
  });
  const query = usePermissionPreview({
    scope: props.scope,
    descriptors,
    enabled: true,
  });
  return <DiscordConfigFields {...props} permissionQuery={query} />;
}

function DiscordConfigFields<T extends FieldValues & DiscordFields>({
  control: parentControl,
  permissionScope,
  canCheckPermissions = false,
  permissionQuery,
  isRepeater,
  organizationId,
  showNotifyNewEvents = isRepeater,
  previewContext,
  showSignupReminder = isRepeater,
}: DiscordConfigSectionProps<T> & { permissionQuery?: PermissionQuery }) {
  // T extends DiscordFields by the generic constraint, so narrowing to
  // Control<DiscordFields> is sound: we touch only the discord-config slice.
  const control = parentControl as unknown as Control<DiscordFields>;
  const values = useWatch({ control }) as DiscordFields;
  const descriptors = settingsDescriptors(values, {
    isRepeater,
    showNotifyNewEvents,
    showSignupReminder,
  });
  const resultFor = (key: string): PermissionCheckResult | undefined => {
    const descriptor = descriptors.find((d) => d.key === key);
    if (!descriptor) return undefined;
    const noServer: PermissionCheckResult = {
      ...descriptor,
      status: 'unconfigured',
      reason: 'no_server_configured',
      destination: {
        kind: 'none',
        channel_id: null,
        parent_id: null,
        name: null,
        channel_type: null,
        source: null,
      },
      required_all: [],
      required_any: [],
      missing: [],
      granted: null,
      effective_permissions: null,
      raw_permissions: null,
      base_granted: null,
      bypass: null,
      blockers: [],
      checked_at: null,
      expires_at: null,
      retry_after_seconds: null,
      refresh_state: null,
    };
    return permissionScope ? permissionQuery?.results.get(key) : noServer;
  };
  const diagnostic = (key: string) => {
    if (!canCheckPermissions || !descriptors.some((d) => d.key === key))
      return null;
    const operation = SETTINGS_OPERATIONS[key];
    return (
      <DiscordPermissionBadge
        operationLabel={operation.label}
        result={resultFor(key)}
        state={permissionQuery?.state ?? 'idle'}
        disabled={!values[operation.field]}
        data-testid={`discord-permission-badge-${key}`}
      />
    );
  };
  const groups = channelPermissionGroups(values, descriptors);
  const channelLabels: Record<ChannelPicker, string> = {
    signup_post: 'Signup channel',
    announcement: 'Announcement channel',
    attendance_reminder: discordLabel('discord_confirm_attendance_channel_id'),
    profile_reminder: discordLabel('discord_profile_reminder_channel_id'),
    new_event_notice: discordLabel('discord_new_event_channel_id'),
  };
  const channelDiagnostic = (picker: ChannelPicker) => {
    if (!canCheckPermissions) return null;
    const group = groups.get(picker);
    if (!group) {
      const descriptor = descriptors.find((d) => d.key === picker);
      const owner = descriptor?.channel_id
        ? [...groups].find(
            ([, g]) => g.channelId === descriptor.channel_id,
          )?.[0]
        : picker === 'signup_post' && values.discord_announcement
          ? 'announcement'
          : undefined;
      if (owner)
        return (
          <p
            data-testid={`discord-permission-shared-${picker}`}
            className="text-sm text-muted-foreground"
          >
            Permissions shown on {channelLabels[owner]}.
          </p>
        );
    }
    const checks = (group?.checks ?? []).map((descriptor) => ({
      operationLabel: channelUseLabel(descriptor, values),
      settingLabel: SETTING_LABELS[descriptor.key],
      result: resultFor(descriptor.key),
    }));
    return (
      <DiscordPermissionBadge
        channel
        operationLabel={channelLabels[picker]}
        result={checks[0]?.result}
        checks={checks}
        state={permissionQuery?.state ?? 'idle'}
        data-testid={`discord-permission-badge-${picker}`}
      />
    );
  };

  const [
    createEvent,
    signupReminder,
    profileReminder,
    confirmAttendance,
    postSignups,
    postSignupsChannelId,
    announcement,
    announcementChannelId,
    startMention,
    notifyNewEvents,
    attendanceChannelId,
    profileChannelId,
    newEventChannelId,
  ] = useWatch({
    control,
    name: [
      'discord_create_event',
      'discord_signup_reminder',
      'discord_profile_reminder',
      'discord_confirm_attendance',
      'discord_post_signups',
      'discord_post_signups_channel_id',
      'discord_announcement',
      'discord_announcement_channel_id',
      'discord_start_mention',
      'discord_notify_new_events',
      'discord_confirm_attendance_channel_id',
      'discord_profile_reminder_channel_id',
      'discord_new_event_channel_id',
    ],
  });

  const channelUsers = fallbackChannelUsers({
    announcement,
    postSignups,
    signupChannelId: postSignupsChannelId,
    confirmAttendance,
    attendanceChannelId,
    profileReminder,
    profileChannelId,
    notifyNewEvents,
    newEventChannelId,
    showNotifyNewEvents,
  });
  const showFallbackBlock = !announcement && channelUsers.length > 0;
  const blankState = (post: ChannelPost) =>
    postChannelState(post, {
      announcement,
      announcementChannelId,
      signupChannelId: '',
      attendanceChannelId: '',
      profileChannelId: '',
      newEventChannelId: '',
    });
  const prerequisite = startMentionPrerequisite({
    postSignups,
    signupChannelId: postSignupsChannelId,
    announcement,
    announcementChannelId,
  });
  const prerequisiteMessage = startMentionPrerequisiteMessage(prerequisite);
  const preview = (kind: PreviewKind) => (
    <EventDiscordPreviewButton
      kind={kind}
      organizationId={organizationId}
      context={previewContext}
    />
  );

  return (
    <div className="space-y-4">
      {permissionQuery && (
        <RecheckPermissionsButton
          onRecheck={permissionQuery.recheck}
          isRechecking={permissionQuery.isRechecking}
          data-testid="discord-permission-recheck"
        />
      )}
      <Subsection testId="discord-subsection-server-event" title="Server event">
        <div className="rounded-md border border-border p-3 space-y-3">
          <CheckboxField
            control={control}
            name="discord_create_event"
            diagnostic={diagnostic('scheduled_event_create')}
            label="Create Discord scheduled event"
            description="Automatically creates a scheduled event in your Discord server"
            action={preview('scheduled_event')}
          />
          {createEvent && (
            <div className="space-y-3 ml-7">
              <CheckboxField
                control={control}
                name="discord_sync_signups"
                diagnostic={diagnostic('scheduled_event_update')}
                label="Synchronize signups"
                description="Keep website and Discord event signups in sync"
                action={preview('scheduled_event_sync')}
              />
              <CheckboxField
                control={control}
                name="discord_mark_interested"
                diagnostic={diagnostic('mark_interested')}
                label="Mark signups as interested"
                description="Players who sign up will be marked as interested on the Discord event"
              />
              <FormField
                control={control}
                name="discord_event_title"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Event title</FormLabel>
                    <FormControl>
                      <Input
                        placeholder="Leave blank to use event name"
                        {...field}
                      />
                    </FormControl>
                    <FormDescription>
                      Custom title for the Discord event. If blank, the event
                      name is used.
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={control}
                name="discord_event_description"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Event description</FormLabel>
                    <FormControl>
                      <Textarea
                        placeholder="Discord event description"
                        rows={2}
                        {...field}
                      />
                    </FormControl>
                    <FormDescription>
                      Shown as the main description of the Discord scheduled
                      event
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={control}
                name="discord_event_info"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Additional info</FormLabel>
                    <FormControl>
                      <Textarea
                        placeholder="Extra details, rules, links..."
                        rows={2}
                        {...field}
                      />
                    </FormControl>
                    <FormDescription>
                      Extra information appended to the Discord event details
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>
          )}
        </div>
      </Subsection>

      <Subsection
        testId="discord-subsection-channel-posts"
        title="Channel posts"
      >
        {/* Post event signup embed */}
        <div className="rounded-md border border-border p-3 space-y-3">
          <CheckboxField
            control={control}
            name="discord_post_signups"
            label="Post event signup embed"
            description="Post an embed to a channel where users can react to sign up"
            action={preview('signup_post')}
          />
          {postSignups && (
            <div className="ml-7 space-y-3">
              <PostChannelField
                control={control}
                name="discord_post_signups_channel_id"
                diagnostic={channelDiagnostic('signup_post')}
                label="Signup channel"
                description="Channel where the signup embed will be posted"
                organizationId={organizationId}
                blankState={blankState('signup')}
                noChannelWarning={SIGNUP_NO_CHANNEL_WARNING}
                data-testid="discord-signup-channel-select"
              />
              <FormField
                control={control}
                name="discord_signup_role_ids"
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
                    <FormDescription>
                      Discord role IDs to @mention in the signup post
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>
          )}
        </div>

        {/* Start mention */}
        <div className="rounded-md border border-border p-3 space-y-3">
          <CheckboxField
            control={control}
            name="discord_start_mention"
            diagnostic={diagnostic('start_mention')}
            label="Mention signed-up members before start"
            description="Reply to the signup post with an @mention of every signed-up member shortly before the event starts"
            action={preview('start_mention')}
          />
          {startMention && (
            <>
              <div className="ml-7 space-y-2">
                <p
                  data-testid="discord-start-mention-prerequisite-note"
                  className="text-sm text-muted-foreground"
                >
                  {START_MENTION_PREREQUISITE_NOTE}
                </p>
                {prerequisite.kind === 'missing' && (
                  <Alert
                    data-testid="discord-start-mention-prerequisite-warning"
                    className="border-warning/30 bg-warning/10 text-warning [&>svg]:text-warning"
                  >
                    <TriangleAlert />
                    <AlertDescription>{prerequisiteMessage}</AlertDescription>
                  </Alert>
                )}
                {prerequisite.kind === 'announcement_fallback' && (
                  <p
                    data-testid="discord-start-mention-prerequisite-fallback"
                    className="text-sm text-muted-foreground"
                  >
                    {prerequisiteMessage}
                  </p>
                )}
              </div>
              <HoursSelect
                control={control}
                name="discord_start_mention_minutes"
                options={START_MENTION_MINUTES_OPTIONS}
              />
              <div className="ml-7">
                <FormField
                  control={control}
                  name="discord_start_mention_scope"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Who to mention</FormLabel>
                      <Select
                        onValueChange={field.onChange}
                        value={field.value}
                      >
                        <FormControl>
                          <SelectTrigger
                            className="w-full"
                            data-testid="discord-discord_start_mention_scope-select"
                          >
                            <SelectValue />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          {START_MENTION_SCOPE_OPTIONS.map((opt) => (
                            <SelectItem key={opt.value} value={opt.value}>
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
            </>
          )}
        </div>

        {/* Pre-day announcement */}
        <div className="rounded-md border border-border p-3 space-y-3">
          <CheckboxField
            control={control}
            name="discord_announcement"
            label="Pre-day announcement"
            description="Post an announcement in a channel before the event"
            action={preview('announcement_notice')}
          />
          {announcement && (
            <div className="ml-7 space-y-3">
              <AnnouncementChannelField
                control={control}
                organizationId={organizationId}
                diagnostic={channelDiagnostic('announcement')}
                lead="Channel for the pre-day announcement. Posts with no channel of their own use it too."
                users={channelUsers}
              />
              <FormField
                control={control}
                name="discord_announcement_hours"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Hours before event</FormLabel>
                    <FormControl>
                      <IntegerInput
                        min={1}
                        name={field.name}
                        ref={field.ref}
                        onBlur={field.onBlur}
                        value={field.value}
                        onValueChange={(v) => v != null && field.onChange(v)}
                      />
                    </FormControl>
                    <FormDescription>
                      How many hours before the event to post the announcement
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={control}
                name="discord_announcement_role_ids"
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
                    <FormDescription>
                      Discord role IDs to @mention when announcement is posted
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>
          )}
        </div>

        {/* Attendance reminder */}
        <div className="rounded-md border border-border p-3 space-y-3">
          <CheckboxField
            control={control}
            name="discord_confirm_attendance"
            label="Post attendance reminder in Discord"
            description={ATTENDANCE_REMINDER_DESCRIPTION}
            action={preview('attendance_reminder')}
          />
          {confirmAttendance && (
            <>
              <HoursSelect
                control={control}
                name="discord_confirm_attendance_hours"
              />
              <div className="ml-7">
                <PostChannelField
                  control={control}
                  name="discord_confirm_attendance_channel_id"
                  diagnostic={channelDiagnostic('attendance_reminder')}
                  label={discordLabel('discord_confirm_attendance_channel_id')}
                  organizationId={organizationId}
                  blankState={blankState('attendance')}
                  noChannelWarning={NO_CHANNEL_WARNING}
                  data-testid="discord-confirm-attendance-channel-select"
                />
              </div>
            </>
          )}
        </div>

        {/* Profile reminder */}
        <div className="rounded-md border border-border p-3 space-y-3">
          <CheckboxField
            control={control}
            name="discord_profile_reminder"
            label="Profile update reminder"
            description={PROFILE_REMINDER_DESCRIPTION}
            action={preview('profile_reminder')}
          />
          {profileReminder && (
            <>
              <HoursSelect
                control={control}
                name="discord_profile_reminder_hours"
              />
              <div className="ml-7">
                <PostChannelField
                  control={control}
                  name="discord_profile_reminder_channel_id"
                  diagnostic={channelDiagnostic('profile_reminder')}
                  label={discordLabel('discord_profile_reminder_channel_id')}
                  organizationId={organizationId}
                  blankState={blankState('profile')}
                  noChannelWarning={NO_CHANNEL_WARNING}
                  data-testid="discord-profile-reminder-channel-select"
                />
              </div>
            </>
          )}
        </div>

        {/* New-event channel post — repeater only */}
        {showNotifyNewEvents && (
          <div className="rounded-md border border-border p-3 space-y-3">
            <CheckboxField
              control={control}
              name="discord_notify_new_events"
              label="Post new events"
              description={NEW_EVENTS_DESCRIPTION}
              action={preview('new_event_post')}
            />
            {notifyNewEvents && (
              <div className="ml-7">
                <PostChannelField
                  control={control}
                  name="discord_new_event_channel_id"
                  diagnostic={channelDiagnostic('new_event_notice')}
                  label={discordLabel('discord_new_event_channel_id')}
                  organizationId={organizationId}
                  blankState={blankState('newEvent')}
                  noChannelWarning={NO_CHANNEL_WARNING}
                  data-testid="discord-new-event-channel-select"
                />
              </div>
            )}
          </div>
        )}

        {showFallbackBlock && (
          <div
            className="rounded-md border border-border p-3"
            data-testid="discord-announcement-channel-block"
          >
            <AnnouncementChannelField
              control={control}
              organizationId={organizationId}
              diagnostic={channelDiagnostic('announcement')}
              lead="Used by posts with no channel of their own."
              users={channelUsers}
            />
          </div>
        )}
      </Subsection>

      <Subsection
        testId="discord-subsection-direct-messages"
        title="Direct messages"
      >
        {showSignupReminder ? (
          <div className="rounded-md border border-border p-3 space-y-3">
            <CheckboxField
              control={control}
              name="discord_signup_reminder"
              diagnostic={diagnostic('signup_reminder')}
              label={
                isRepeater
                  ? SIGNUP_REMINDER_LABEL
                  : `${SIGNUP_REMINDER_LABEL} (default for new series)`
              }
              description={signupReminderMeta.description ?? ''}
              action={preview('signup_reminder')}
            />
            <p
              className="ml-7 text-sm text-muted-foreground"
              data-testid="discord-signup-reminder-subscribe-note"
            >
              {SUBSCRIBE_NOTE}
            </p>
            {signupReminder && (
              <HoursSelect
                control={control}
                name="discord_signup_reminder_hours"
                label="Hours before event"
              />
            )}
          </div>
        ) : (
          <p
            className="text-sm text-muted-foreground"
            data-testid="discord-direct-messages-series-only"
          >
            Direct messages are set on recurring series.
          </p>
        )}
      </Subsection>
    </div>
  );
}
