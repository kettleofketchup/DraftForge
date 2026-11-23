import { RotateCcw } from 'lucide-react';
import type { ComponentProps, ReactNode } from 'react';
import {
  useWatch,
  type Control,
  type FieldValues,
  type Path,
  type PathValue,
  type UseFormSetValue,
} from 'react-hook-form';

import { Badge } from '~/components/ui/badge';
import { SecondaryButton } from '~/components/ui/buttons';
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

export function SettingsGroup({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <fieldset className="flex flex-col gap-4">
      <legend className="mb-4 text-sm font-semibold">{title}</legend>
      {children}
    </fieldset>
  );
}

export function SettingNumberInput({
  value,
  onChange,
  ...props
}: Omit<ComponentProps<typeof Input>, 'value' | 'onChange'> & {
  value: number | undefined;
  onChange: (value: number) => void;
}) {
  return (
    <Input
      type="number"
      inputMode="decimal"
      className="w-full sm:w-40"
      value={value === undefined || Number.isNaN(value) ? '' : value}
      onChange={(e) =>
        onChange(e.target.value === '' ? Number.NaN : Number(e.target.value))
      }
      {...props}
    />
  );
}

export interface SettingProps<
  TForm extends FieldValues,
  N extends Path<TForm>,
> {
  control: Control<TForm>;
  setValue: UseFormSetValue<TForm>;
  name: N;
  label: string;
  help: string;
  defaultValue: PathValue<TForm, N>;
  testIdPrefix: string;
}

function settingTestId(prefix: string, name: string): string {
  return `${prefix}-${name.replaceAll('.', '-')}`;
}

function DefaultControls<TForm extends FieldValues, N extends Path<TForm>>({
  control,
  setValue,
  name,
  label,
  defaultValue,
  testIdPrefix,
}: Omit<SettingProps<TForm, N>, 'help'>) {
  const value = useWatch({ control, name });
  const isDefault = value === defaultValue;
  const testId = settingTestId(testIdPrefix, name);
  return (
    <div className="flex items-center gap-2">
      {isDefault && (
        <Badge variant="outline" data-testid={`${testId}-default`}>
          Default
        </Badge>
      )}
      <SecondaryButton
        type="button"
        size="sm"
        data-testid={`${testId}-reset`}
        aria-label={`Reset ${label} to default`}
        disabled={isDefault}
        onClick={() =>
          setValue(name, defaultValue, {
            shouldDirty: true,
            shouldValidate: true,
          })
        }
      >
        <RotateCcw data-icon="inline-start" />
        Reset
      </SecondaryButton>
    </div>
  );
}

export function NumberSetting<
  TForm extends FieldValues,
  N extends Path<TForm>,
>({ step, ...props }: SettingProps<TForm, N> & { step: number }) {
  const { control, name, label, help, testIdPrefix } = props;
  return (
    <FormField
      control={control}
      name={name}
      render={({ field }) => (
        <FormItem>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <FormLabel>{label}</FormLabel>
            <DefaultControls {...props} />
          </div>
          <FormControl>
            <SettingNumberInput
              step={step}
              data-testid={settingTestId(testIdPrefix, name)}
              name={field.name}
              ref={field.ref}
              onBlur={field.onBlur}
              value={field.value}
              onChange={field.onChange}
            />
          </FormControl>
          <FormDescription>{help}</FormDescription>
          <FormMessage />
        </FormItem>
      )}
    />
  );
}

export function ToggleSetting<TForm extends FieldValues, N extends Path<TForm>>(
  props: SettingProps<TForm, N>,
) {
  const { control, name, label, help, testIdPrefix } = props;
  return (
    <FormField
      control={control}
      name={name}
      render={({ field }) => (
        <FormItem>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-3">
              <FormControl>
                <Switch
                  data-testid={settingTestId(testIdPrefix, name)}
                  checked={field.value}
                  onCheckedChange={field.onChange}
                  onBlur={field.onBlur}
                  ref={field.ref}
                />
              </FormControl>
              <FormLabel>{label}</FormLabel>
            </div>
            <DefaultControls {...props} />
          </div>
          <FormDescription>{help}</FormDescription>
          <FormMessage />
        </FormItem>
      )}
    />
  );
}
