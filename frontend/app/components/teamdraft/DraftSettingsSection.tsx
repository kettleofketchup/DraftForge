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
import { Switch } from '~/components/ui/switch';
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

  const timerSwitch = (
    name: 'draft_timer_enabled' | 'hero_timer_enabled',
    label: string,
    testId: string,
    seconds: SecondsField[],
  ) => (
    <FormField
      control={control}
      name={name}
      render={({ field }) => (
        <FormItem className="flex items-center justify-between">
          <FormLabel>{label}</FormLabel>
          <FormControl>
            <Switch
              checked={field.value}
              onCheckedChange={(on) => {
                field.onChange(on);
                if (!on) resetInvalid(seconds);
              }}
              data-testid={testId}
            />
          </FormControl>
        </FormItem>
      )}
    />
  );

  const secondsInput = (name: SecondsField, label: string, testId: string) => (
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
          <FormMessage />
        </FormItem>
      )}
    />
  );

  return (
    <div className="space-y-3 mt-4" data-testid="draft-settings-section">
      <h3 className="text-sm font-semibold">Draft Settings</h3>
      <div className="rounded-md border border-border p-3 space-y-4">
        {showDraftType && (
          <FormField
            control={control}
            name="draft_type"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Team draft type</FormLabel>
                <Select onValueChange={field.onChange} value={field.value}>
                  <FormControl>
                    <SelectTrigger
                      className="w-full"
                      data-testid="draft-settings-draft-type"
                    >
                      <SelectValue />
                    </SelectTrigger>
                  </FormControl>
                  <SelectContent>
                    {DRAFT_STYLE_VALUES.map((v) => (
                      <SelectItem
                        key={v}
                        value={v}
                        data-testid={`draft-settings-draft-type-${v}`}
                      >
                        {DRAFT_STYLE_LABELS[v]}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <FormMessage />
              </FormItem>
            )}
          />
        )}

        <div className="space-y-3" data-testid="draft-settings-team">
          <h4 className="text-sm font-medium text-muted-foreground">
            Team draft
          </h4>
          {timerSwitch(
            'draft_timer_enabled',
            'Turn timer',
            'draft-settings-team-timer-enabled',
            ['draft_grace_time_s', 'draft_reserve_time_s'],
          )}
          {teamTimerOn ? (
            <>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                {secondsInput(
                  'draft_grace_time_s',
                  'Grace time (s)',
                  'draft-settings-team-grace-s',
                )}
                {secondsInput(
                  'draft_reserve_time_s',
                  'Reserve time (s)',
                  'draft-settings-team-reserve-s',
                )}
              </div>
              {showTimeoutAction && (
                <FormField
                  control={control}
                  name="draft_timeout_action"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>On timeout</FormLabel>
                      <Select
                        onValueChange={field.onChange}
                        value={field.value}
                      >
                        <FormControl>
                          <SelectTrigger
                            className="w-full"
                            data-testid="draft-settings-team-timeout-action"
                          >
                            <SelectValue />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          {TIMEOUT_ACTION_VALUES.map((v) => (
                            <SelectItem
                              key={v}
                              value={v}
                              data-testid={`draft-settings-team-timeout-action-${v}`}
                            >
                              {TIMEOUT_ACTION_LABELS[v]}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              )}
            </>
          ) : (
            <FormDescription>
              Captains pick without a time limit
            </FormDescription>
          )}
        </div>

        <div className="space-y-3" data-testid="draft-settings-hero">
          <h4 className="text-sm font-medium text-muted-foreground">
            Hero draft
          </h4>
          {timerSwitch(
            'hero_timer_enabled',
            'Turn timer',
            'draft-settings-hero-timer-enabled',
            ['hero_grace_time_s', 'hero_reserve_time_s'],
          )}
          {heroTimerOn ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {secondsInput(
                'hero_grace_time_s',
                'Grace time per pick (s)',
                'draft-settings-hero-grace-s',
              )}
              {secondsInput(
                'hero_reserve_time_s',
                'Reserve time per team (s)',
                'draft-settings-hero-reserve-s',
              )}
            </div>
          ) : (
            <FormDescription>
              Hero picks and bans have no time limit
            </FormDescription>
          )}
        </div>
      </div>
    </div>
  );
}
