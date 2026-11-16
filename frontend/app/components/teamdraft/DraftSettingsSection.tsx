import type { ReactNode } from 'react';
import {
  useFormContext,
  useWatch,
  type Control,
  type FieldValues,
} from 'react-hook-form';
import {
  BrandSelect,
  BrandSelectContent,
  BrandSelectItem,
  BrandSelectTrigger,
  SelectValue,
} from '~/components/ui/brand-select';
import {
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '~/components/ui/form';
import { Input } from '~/components/ui/input';
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
    testId: string,
    seconds: SecondsField[],
  ) => (
    <FormField
      control={control}
      name={name}
      render={({ field }) => (
        <FormItem className="ml-auto flex items-center gap-2 space-y-0">
          <FormLabel className="text-sm font-normal text-muted-foreground">
            Turn timer
          </FormLabel>
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
          <div className="flex items-center gap-2">
            <FormControl>
              <Input
                type="number"
                step="1"
                min={DRAFT_SETTINGS_SECONDS_MIN[name]}
                className="w-24"
                data-testid={testId}
                name={field.name}
                ref={field.ref}
                onBlur={field.onBlur}
                value={field.value as string | number}
                onChange={(e) => field.onChange(e.target.value)}
              />
            </FormControl>
            <span className="text-sm text-muted-foreground">s</span>
          </div>
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
  ) => (
    <FormField
      control={control}
      name={name}
      render={({ field }) => (
        <FormItem>
          <FormLabel>{label}</FormLabel>
          <BrandSelect onValueChange={field.onChange} value={field.value}>
            <FormControl>
              <BrandSelectTrigger className="w-full" data-testid={testId}>
                <SelectValue />
              </BrandSelectTrigger>
            </FormControl>
            <BrandSelectContent>
              {values.map((v) => (
                <BrandSelectItem
                  key={v}
                  value={v}
                  data-testid={`${testId}-${v}`}
                >
                  {labels[v]}
                </BrandSelectItem>
              ))}
            </BrandSelectContent>
          </BrandSelect>
          <FormMessage />
        </FormItem>
      )}
    />
  );

  return (
    <div
      className="@container mt-4 flex flex-col gap-3"
      data-testid="draft-settings-section"
    >
      <h3 className="text-sm font-semibold">Draft settings</h3>
      <div className="grid grid-cols-1 gap-3 @2xl:grid-cols-2">
        <SettingsCard
          title="Team draft"
          testId="draft-settings-team"
          toggle={timerSwitch(
            'draft_timer_enabled',
            'draft-settings-team-timer-enabled',
            ['draft_grace_time_s', 'draft_reserve_time_s'],
          )}
        >
          {showDraftType &&
            select(
              'draft_type',
              'Draft type',
              DRAFT_STYLE_VALUES,
              DRAFT_STYLE_LABELS,
              'draft-settings-draft-type',
            )}
          {teamTimerOn ? (
            <>
              <div className="flex flex-wrap gap-x-6 gap-y-3">
                {secondsInput(
                  'draft_grace_time_s',
                  'Grace time',
                  'draft-settings-team-grace-s',
                )}
                {secondsInput(
                  'draft_reserve_time_s',
                  'Reserve time',
                  'draft-settings-team-reserve-s',
                )}
              </div>
              {showTimeoutAction &&
                select(
                  'draft_timeout_action',
                  'On timeout',
                  TIMEOUT_ACTION_VALUES,
                  TIMEOUT_ACTION_LABELS,
                  'draft-settings-team-timeout-action',
                )}
            </>
          ) : (
            <FormDescription>
              Captains pick without a time limit
            </FormDescription>
          )}
        </SettingsCard>

        <SettingsCard
          title="Hero draft"
          testId="draft-settings-hero"
          toggle={timerSwitch(
            'hero_timer_enabled',
            'draft-settings-hero-timer-enabled',
            ['hero_grace_time_s', 'hero_reserve_time_s'],
          )}
        >
          {heroTimerOn ? (
            <div className="flex flex-wrap gap-x-6 gap-y-3">
              {secondsInput(
                'hero_grace_time_s',
                'Grace per pick',
                'draft-settings-hero-grace-s',
              )}
              {secondsInput(
                'hero_reserve_time_s',
                'Reserve per team',
                'draft-settings-hero-reserve-s',
              )}
            </div>
          ) : (
            <FormDescription>
              Hero picks and bans have no time limit
            </FormDescription>
          )}
        </SettingsCard>
      </div>
    </div>
  );
}

function SettingsCard({
  title,
  testId,
  toggle,
  children,
}: {
  title: string;
  testId: string;
  toggle: ReactNode;
  children: ReactNode;
}) {
  return (
    <div
      className="flex flex-col gap-4 rounded-md border border-border bg-base-300 p-4"
      data-testid={testId}
    >
      <div className="flex items-center gap-3">
        <h4 className="text-sm font-semibold">{title}</h4>
        {toggle}
      </div>
      {children}
    </div>
  );
}
