import {
  useFormContext,
  useWatch,
  type Control,
  type FieldValues,
} from 'react-hook-form';
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
import {
  DRAFT_SETTINGS_SECONDS_MIN,
  DRAFT_STYLE_LABELS,
  DRAFT_STYLE_VALUES,
  TIMEOUT_ACTION_LABELS,
  TIMEOUT_ACTION_VALUES,
  isValidSeconds,
  type DraftSettingsFormInput,
} from './schemas';

type DraftSettingsFields = DraftSettingsFormInput & { draft_type?: string };
type SecondsField = keyof typeof DRAFT_SETTINGS_SECONDS_MIN;

interface Props<T extends FieldValues & DraftSettingsFields> {
  control: Control<T>;
  showDraftType?: boolean;
  showTimeoutAction?: boolean;
}

export function DraftSettingsSection<
  T extends FieldValues & DraftSettingsFields,
>({
  control: parentControl,
  showDraftType = true,
  showTimeoutAction = true,
}: Props<T>) {
  const control = parentControl as unknown as Control<DraftSettingsFields>;
  const { getValues, resetField } = useFormContext<DraftSettingsFields>();
  const teamTimerOn = useWatch({ control, name: 'draft_timer_enabled' });
  const heroTimerOn = useWatch({ control, name: 'hero_timer_enabled' });

  // Hidden inputs can't be fixed, so drop invalid edits when the timer goes off.
  const resetInvalid = (names: SecondsField[]) => {
    for (const name of names) {
      if (!isValidSeconds(getValues(name), DRAFT_SETTINGS_SECONDS_MIN[name])) {
        resetField(name);
      }
    }
  };

  const timerCheckbox = (
    name: 'draft_timer_enabled' | 'hero_timer_enabled',
    testId: string,
    label: string,
    description: string,
    seconds: SecondsField[],
  ) => (
    <FormField
      control={control}
      name={name}
      render={({ field }) => (
        <FormItem className="flex items-center gap-3">
          <FormControl>
            <input
              type="checkbox"
              data-testid={testId}
              checked={!!field.value}
              name={field.name}
              ref={field.ref}
              onBlur={field.onBlur}
              onChange={(e) => {
                const on = e.target.checked;
                field.onChange(on);
                if (!on) resetInvalid(seconds);
              }}
              className="h-4 w-4 rounded border-border accent-primary"
            />
          </FormControl>
          <div>
            <FormLabel className="text-sm font-medium cursor-pointer">
              {label}
            </FormLabel>
            <FormDescription>{description}</FormDescription>
          </div>
        </FormItem>
      )}
    />
  );

  const secondsInput = (
    name: SecondsField,
    label: string,
    description: string,
    testId: string,
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
              min={DRAFT_SETTINGS_SECONDS_MIN[name]}
              data-testid={testId}
              name={field.name}
              ref={field.ref}
              onBlur={field.onBlur}
              value={field.value as string | number}
              onChange={(e) => field.onChange(e.target.value)}
            />
          </FormControl>
          <FormDescription>{description}</FormDescription>
          <FormMessage />
        </FormItem>
      )}
    />
  );

  const select = <V extends string>(
    name: 'draft_type' | 'draft_timeout_action',
    label: string,
    values: readonly V[],
    labels: Record<V, string>,
    testId: string,
    description: string,
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
          <FormDescription>{description}</FormDescription>
          <FormMessage />
        </FormItem>
      )}
    />
  );

  // Bare Select, not BrandSelect: these dialogs use neutral shadcn selects and the brand trigger clashes (component-substitutions.md exception).
  return (
    <div className="flex flex-col gap-3" data-testid="draft-settings-section">
      <div className="flex flex-col gap-1">
        <h3 className="text-sm font-semibold">Draft settings</h3>
        <p className="text-xs text-muted-foreground">
          Optional turn timers for captains' player picks and for hero picks and
          bans.
        </p>
      </div>

      {showDraftType &&
        select(
          'draft_type',
          'Draft type',
          DRAFT_STYLE_VALUES,
          DRAFT_STYLE_LABELS,
          'draft-settings-draft-type',
          'How captains build their teams',
        )}

      <div
        className="rounded-md border border-border p-3 flex flex-col gap-3"
        data-testid="draft-settings-team"
      >
        {timerCheckbox(
          'draft_timer_enabled',
          'draft-settings-team-timer-enabled',
          'Team draft timer',
          'Captains get a countdown for each player pick. Unchecked, they pick without a time limit.',
          ['draft_grace_time_s', 'draft_reserve_time_s'],
        )}
        {teamTimerOn && (
          <div className="ml-7 grid grid-cols-1 gap-4 border-l-2 border-primary/20 pl-4 sm:grid-cols-2">
            {secondsInput(
              'draft_grace_time_s',
              'Grace time (seconds)',
              'Resets every pick',
              'draft-settings-team-grace-s',
            )}
            {secondsInput(
              'draft_reserve_time_s',
              'Reserve time (seconds)',
              'Bank each captain draws on after grace runs out',
              'draft-settings-team-reserve-s',
            )}
            {showTimeoutAction &&
              select(
                'draft_timeout_action',
                'On timeout',
                TIMEOUT_ACTION_VALUES,
                TIMEOUT_ACTION_LABELS,
                'draft-settings-team-timeout-action',
                'When grace and reserve both run out',
              )}
          </div>
        )}
      </div>

      <div
        className="rounded-md border border-border p-3 flex flex-col gap-3"
        data-testid="draft-settings-hero"
      >
        {timerCheckbox(
          'hero_timer_enabled',
          'draft-settings-hero-timer-enabled',
          'Hero draft timer',
          'Each team gets a countdown for hero picks and bans. Unchecked, there is no time limit.',
          ['hero_grace_time_s', 'hero_reserve_time_s'],
        )}
        {heroTimerOn && (
          <div className="ml-7 grid grid-cols-1 gap-4 border-l-2 border-primary/20 pl-4 sm:grid-cols-2">
            {secondsInput(
              'hero_grace_time_s',
              'Grace per pick (seconds)',
              'Resets every pick or ban',
              'draft-settings-hero-grace-s',
            )}
            {secondsInput(
              'hero_reserve_time_s',
              'Reserve per team (seconds)',
              'Shared bank for the whole hero draft',
              'draft-settings-hero-reserve-s',
            )}
          </div>
        )}
      </div>
    </div>
  );
}
