import { ChevronRight } from 'lucide-react';
import { useEffect, useState, type ReactNode } from 'react';
import {
  useFormContext,
  useFormState,
  useWatch,
  type Control,
  type FieldPath,
  type FieldValues,
  type PathValue,
  type UseFormSetValue,
} from 'react-hook-form';
import type { z } from 'zod';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '~/components/ui/collapsible';
import {
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '~/components/ui/form';
import { Input } from '~/components/ui/input';
import { Label } from '~/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '~/components/ui/select';
import { Switch } from '~/components/ui/switch';
import { cn } from '~/lib/utils';
import { DiscordChannelPicker } from './DiscordChannelPicker';
import { READY_CHECK_TEST_IDS as IDS } from './form/testIds';
import {
  LOW_COMPLETION_ACTIONS,
  LOW_COMPLETION_ACTION_LABELS,
  POST_CULL_FILL_MODES,
  POST_CULL_FILL_MODE_LABELS,
  READY_CHECK_CONFIG_DEFAULTS,
  READY_CHECK_PRESET_ON,
  READY_CHECK_SCOPES,
  READY_CHECK_SCOPE_LABELS,
  ROLL_CALL_MODES,
  ROLL_CALL_MODE_LABELS,
  readyCheckConfigSchema,
  refineReadyCheck,
  type ReadyCheckFields,
} from './schemas';

type BooleanField = {
  [K in keyof ReadyCheckFields]: ReadyCheckFields[K] extends boolean
    ? K
    : never;
}[keyof ReadyCheckFields];
type NumberField =
  | 'ready_check_open_minutes'
  | 'ready_check_escalation_minutes'
  | 'ready_check_close_minutes'
  | 'ready_check_chase_minutes'
  | 'ready_check_min_completion_pct'
  | 'start_cull_minutes_after';
type SelectField =
  | 'roll_call_mode'
  | 'ready_check_scope'
  | 'ready_check_low_completion_action'
  | 'post_cull_fill_mode';

const SETTINGS_INPUTS: NumberField[] = [
  'ready_check_open_minutes',
  'ready_check_escalation_minutes',
  'ready_check_close_minutes',
  'ready_check_chase_minutes',
  'ready_check_min_completion_pct',
];
const TIMING_INPUTS: NumberField[] = [
  'ready_check_open_minutes',
  'ready_check_escalation_minutes',
  'ready_check_close_minutes',
  'ready_check_chase_minutes',
];
const SETTINGS_FIELDS: (keyof ReadyCheckFields)[] = [
  ...SETTINGS_INPUTS,
  'roll_call_mode',
  'ready_check_scope',
  'ready_check_low_completion_action',
  'ready_check_notify_on_signup',
  'ready_check_drop_notice',
];
const VOICE_INPUTS: (keyof ReadyCheckFields)[] = [
  'event_voice_channel_id',
  'start_cull_minutes_after',
];
const VOICE_FIELDS: (keyof ReadyCheckFields)[] = [
  ...VOICE_INPUTS,
  'voice_presence_confirms',
  'start_cull_enabled',
  'post_cull_fill_mode',
];
type ReadyCheckFormInput = z.input<typeof readyCheckConfigSchema>;

const refinedSchema = readyCheckConfigSchema.superRefine((values, ctx) =>
  refineReadyCheck(values, ctx),
);

interface Props<T extends FieldValues & ReadyCheckFormInput> {
  control: Control<T>;
  setValue: UseFormSetValue<T>;
  organizationId: number | null;
  showAutoConfirm?: boolean;
}

export function ReadyCheckConfigSection<
  T extends FieldValues & ReadyCheckFormInput,
>({
  control: parentControl,
  setValue: parentSetValue,
  organizationId,
  showAutoConfirm = false,
}: Props<T>) {
  const control = parentControl as unknown as Control<ReadyCheckFields>;
  const setValue =
    parentSetValue as unknown as UseFormSetValue<ReadyCheckFields>;
  const {
    getValues,
    resetField,
    formState: { defaultValues },
  } = useFormContext<ReadyCheckFields>();
  const { errors } = useFormState({ control });
  const hasError = (names: (keyof ReadyCheckFields)[]) =>
    names.some((name) => errors[name]);
  const settingsError = hasError(SETTINGS_FIELDS);
  const voiceError = hasError(VOICE_FIELDS);
  const rollCallOn = useWatch({ control, name: 'roll_call_enabled' });
  const rollCallMode = useWatch({ control, name: 'roll_call_mode' });
  const chase = useWatch({ control, name: 'ready_check_chase_minutes' });
  const pct = useWatch({ control, name: 'ready_check_min_completion_pct' });
  const cullOn = useWatch({ control, name: 'start_cull_enabled' });
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [voiceOpen, setVoiceOpen] = useState(false);
  useEffect(() => {
    if (settingsError) setSettingsOpen(true);
  }, [settingsError]);
  useEffect(() => {
    if (voiceError) setVoiceOpen(true);
  }, [voiceError]);

  // Hidden inputs can't be fixed, so drop invalid edits when they collapse.
  const resetInvalid = (names: (keyof ReadyCheckFields)[]) => {
    for (const name of names) {
      const schema = readyCheckConfigSchema.shape[name];
      if (!schema.safeParse(getValues(name)).success) resetField(name);
    }
  };

  const setDirty = <K extends FieldPath<ReadyCheckFields>>(
    name: K,
    value: PathValue<ReadyCheckFields, K>,
  ) => setValue(name, value, { shouldDirty: true });

  const resetCrossFieldTimings = () => {
    const result = refinedSchema.safeParse(getValues());
    const broken =
      !result.success &&
      result.error.issues.some((issue) =>
        (TIMING_INPUTS as PropertyKey[]).includes(issue.path[0]),
      );
    if (broken) TIMING_INPUTS.forEach((name) => resetField(name));
  };

  const onToggle = (on: boolean) => {
    if (on) {
      setDirty('roll_call_enabled', READY_CHECK_PRESET_ON.roll_call_enabled);
      if (!defaultValues?.roll_call_enabled)
        setDirty('roll_call_mode', READY_CHECK_PRESET_ON.roll_call_mode);
      setDirty('auto_confirm', READY_CHECK_PRESET_ON.auto_confirm);
    } else {
      setDirty('roll_call_enabled', false);
      resetInvalid(SETTINGS_INPUTS);
      resetCrossFieldTimings();
    }
  };

  const switchField = (
    name: BooleanField,
    testId: string,
    label: string,
    description?: string,
    opts: { disabled?: boolean; onChange?: (on: boolean) => void } = {},
  ) => (
    <FormField
      control={control}
      name={name}
      render={({ field }) => (
        <FormItem className="flex items-start gap-3 space-y-0">
          <FormControl>
            <Switch
              data-testid={testId}
              checked={!!field.value}
              disabled={opts.disabled}
              name={field.name}
              ref={field.ref}
              onBlur={field.onBlur}
              onCheckedChange={(on) =>
                opts.onChange ? opts.onChange(on) : field.onChange(on)
              }
              className="mt-0.5"
            />
          </FormControl>
          <div>
            <FormLabel className="text-sm font-medium cursor-pointer">
              {label}
            </FormLabel>
            {description && <FormDescription>{description}</FormDescription>}
            <FormMessage />
          </div>
        </FormItem>
      )}
    />
  );

  const numberInput = (
    name: NumberField,
    label: string,
    description: string,
    testId: string,
    disabled = false,
  ) => (
    <FormField
      control={control}
      name={name}
      render={({ field }) => (
        <FormItem>
          <FormLabel>{label}</FormLabel>
          <FormControl>
            <Input
              type="number"
              step="1"
              data-testid={testId}
              disabled={disabled}
              name={field.name}
              ref={field.ref}
              onBlur={field.onBlur}
              value={
                field.value == null || Number.isNaN(field.value)
                  ? ''
                  : field.value
              }
              onChange={(e) => field.onChange(e.target.valueAsNumber)}
            />
          </FormControl>
          <FormDescription>{description}</FormDescription>
          <FormMessage />
        </FormItem>
      )}
    />
  );

  // Bare Select, not BrandSelect: these dialogs use neutral shadcn selects and the brand trigger clashes (component-substitutions.md exception).
  const select = <V extends string>(
    name: SelectField,
    label: string,
    values: readonly V[],
    labels: Record<V, string>,
    testId: string,
    description?: string,
  ) => (
    <FormField
      control={control}
      name={name}
      render={({ field }) => (
        <FormItem>
          <FormLabel>{label}</FormLabel>
          <Select onValueChange={field.onChange} value={field.value}>
            <FormControl>
              <SelectTrigger className="w-full" data-testid={testId}>
                <SelectValue />
              </SelectTrigger>
            </FormControl>
            <SelectContent>
              {values.map((v) => (
                <SelectItem key={v} value={v} data-testid={`${testId}-${v}`}>
                  {labels[v]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {description && <FormDescription>{description}</FormDescription>}
          <FormMessage />
        </FormItem>
      )}
    />
  );

  const block = (
    open: boolean,
    onOpenChange: (open: boolean) => void,
    testId: string,
    fields: readonly (keyof ReadyCheckFields)[],
    title: string,
    children: ReactNode,
    disabled = false,
  ) => (
    <Collapsible
      open={open}
      onOpenChange={onOpenChange}
      disabled={disabled}
      // Lets the settings search find and open fields while collapsed.
      data-fields={fields.join(' ')}
      className="rounded-md border border-border"
    >
      <CollapsibleTrigger
        data-testid={testId}
        className={cn(
          'flex w-full min-h-11 items-center gap-2 px-3 py-2 text-sm font-medium',
          'hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
          'disabled:cursor-not-allowed disabled:opacity-50',
        )}
      >
        <ChevronRight
          className={cn('size-4 transition-transform', open && 'rotate-90')}
        />
        {title}
      </CollapsibleTrigger>
      <CollapsibleContent className="flex flex-col gap-4 px-3 pb-3">
        {children}
      </CollapsibleContent>
    </Collapsible>
  );

  return (
    <div className="flex flex-col gap-3" data-testid={IDS.section}>
      <div className="rounded-md border border-border p-3 flex flex-col gap-3">
        {switchField(
          'roll_call_enabled',
          IDS.toggle,
          'Mandatory RSVP Confirmation',
          rollCallMode === 'automatic'
            ? 'Every rostered member must confirm before teams are made. Automatic drops of unconfirmed members arrive in a later release; until then staff verify roll call.'
            : 'Every rostered member must confirm before teams are made. Staff verify who confirmed; nobody is dropped automatically.',
          { onChange: onToggle },
        )}
        {showAutoConfirm &&
          switchField(
            'auto_confirm',
            IDS.autoConfirm,
            'Auto-confirm signups',
            rollCallOn
              ? 'Off while confirmation is mandatory'
              : 'Signups are marked as confirmed without asking the member',
            { disabled: !!rollCallOn },
          )}
      </div>

      {block(
        (!!rollCallOn && settingsOpen) || settingsError,
        (open) => {
          setSettingsOpen(open);
          if (!open) resetInvalid(SETTINGS_INPUTS);
        },
        IDS.settingsTrigger,
        SETTINGS_FIELDS,
        'Ready check settings',
        <>
          <p
            className="text-sm text-muted-foreground"
            data-testid={IDS.settingsNotActive}
          >
            Not active yet: these settings are saved, but no Ready DM, nudge,
            ops notice or automatic drop goes out until the automatic ready
            check ships.
          </p>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            {select(
              'roll_call_mode',
              'Mode',
              ROLL_CALL_MODES,
              ROLL_CALL_MODE_LABELS,
              IDS.mode,
            )}
            {select(
              'ready_check_scope',
              'Who is asked',
              READY_CHECK_SCOPES,
              READY_CHECK_SCOPE_LABELS,
              IDS.scope,
            )}
            {numberInput(
              'ready_check_open_minutes',
              'Opens (minutes)',
              'Minutes before start. Each asked member gets a Ready button by DM.',
              IDS.open,
            )}
            {numberInput(
              'ready_check_escalation_minutes',
              'Nudge unconfirmed members by DM (minutes)',
              'Minutes before start (0 = off). Staff also get the unconfirmed count as an ops notice.',
              IDS.escalation,
            )}
            {numberInput(
              'ready_check_close_minutes',
              'Closes (minutes)',
              'Minutes before start',
              IDS.close,
            )}
            <div className="flex flex-col gap-2">
              {numberInput(
                'ready_check_chase_minutes',
                'Ops notice per unconfirmed member (minutes)',
                'Minutes before close. Shown to org and league staff, the event host and helpers on the event page, and sent wherever the org routes ops notices.',
                IDS.chase,
                chase === null,
              )}
              <div className="flex items-center gap-2">
                <Switch
                  id={IDS.chaseOff}
                  data-testid={IDS.chaseOff}
                  checked={chase === null}
                  onCheckedChange={(off) =>
                    setDirty(
                      'ready_check_chase_minutes',
                      off
                        ? null
                        : READY_CHECK_CONFIG_DEFAULTS.ready_check_chase_minutes,
                    )
                  }
                />
                <Label htmlFor={IDS.chaseOff} className="text-sm font-normal">
                  No per-member ops notices
                </Label>
              </div>
            </div>
          </div>
          <div
            className="grid grid-cols-1 gap-4 sm:grid-cols-2"
            data-testid={`${IDS.minCompletion}-row`}
          >
            {numberInput(
              'ready_check_min_completion_pct',
              'Minimum confirmed (%)',
              `If fewer than ${Number.isFinite(pct) ? pct : '…'}% have confirmed at close…`,
              IDS.minCompletion,
            )}
            {select(
              'ready_check_low_completion_action',
              '…then',
              LOW_COMPLETION_ACTIONS,
              LOW_COMPLETION_ACTION_LABELS,
              IDS.lowCompletionAction,
              'Non-binding and held checks raise an urgent ops notice for staff.',
            )}
          </div>
          {switchField(
            'ready_check_notify_on_signup',
            IDS.notifyOnSignup,
            'DM members on their first sign-up that confirmation is mandatory',
            'If their DMs are closed they get a reply only they can see, and staff get an ops notice.',
          )}
          {switchField(
            'ready_check_drop_notice',
            IDS.dropNotice,
            'DM members who are dropped',
            'Members can turn this off under roster changes in their notification settings.',
          )}
        </>,
        !rollCallOn && !settingsError,
      )}

      {block(
        voiceOpen || voiceError,
        (open) => {
          setVoiceOpen(open);
          if (!open) resetInvalid(VOICE_INPUTS);
        },
        IDS.voiceTrigger,
        VOICE_FIELDS,
        'Start cull and voice',
        <>
          <p
            className="text-sm text-muted-foreground"
            data-testid={IDS.voiceNotActive}
          >
            Not active yet: voice presence and the start cull are saved but do
            not run until a later release.
          </p>
          <FormField
            control={control}
            name="event_voice_channel_id"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Event voice channel</FormLabel>
                <FormControl>
                  {organizationId == null ? (
                    <Input
                      data-testid={IDS.voiceChannel}
                      disabled
                      name={field.name}
                      ref={field.ref}
                      value={field.value}
                      readOnly
                    />
                  ) : (
                    <DiscordChannelPicker
                      organizationId={organizationId}
                      kind="voice"
                      value={field.value}
                      onChange={field.onChange}
                      data-testid={IDS.voiceChannel}
                    />
                  )}
                </FormControl>
                {organizationId == null && (
                  <FormDescription>
                    Needs an organization with a Discord server
                  </FormDescription>
                )}
                <FormMessage />
              </FormItem>
            )}
          />
          {switchField(
            'voice_presence_confirms',
            IDS.voiceConfirms,
            'Count presence in the voice channel as ready',
          )}
          {switchField(
            'start_cull_enabled',
            IDS.cullEnabled,
            'Remove members absent from the voice channel after start',
            'Removed members get the drop notice DM. If the bot cannot see the voice channel, nobody is removed and staff get an ops notice.',
            {
              onChange: (on) => {
                setDirty('start_cull_enabled', on);
                if (!on) resetInvalid(['start_cull_minutes_after']);
              },
            },
          )}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            {numberInput(
              'start_cull_minutes_after',
              'Cull after (minutes)',
              'Minutes after start',
              IDS.cullMinutes,
              !cullOn,
            )}
            {select(
              'post_cull_fill_mode',
              'After the cull, fill open seats by',
              POST_CULL_FILL_MODES,
              POST_CULL_FILL_MODE_LABELS,
              IDS.fillMode,
              'Members moved into a seat get a promotion DM.',
            )}
          </div>
        </>,
      )}
    </div>
  );
}
