import React from 'react';
import type { UseFormReturn } from 'react-hook-form';
import {
  FormControl,
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
  POSITION_LABELS,
  POSITION_OPTIONS,
  positionIcons,
  positionKeys,
  type PositionKey,
} from '~/components/user/positions/positionEdit';
import type { EditUserInput } from './editUserSchema';

interface Props {
  form: UseFormReturn<EditUserInput>;
  showMmr: boolean;
  mmrLabel: string;
}

function PositionSelect({
  form,
  fieldKey,
  label,
  Icon,
}: {
  form: UseFormReturn<EditUserInput>;
  fieldKey: PositionKey;
  label: string;
  Icon: React.FC<{ className?: string }>;
}) {
  return (
    <FormField
      control={form.control}
      name={`positions.${fieldKey}` as const}
      render={({ field }) => (
        <FormItem>
          <FormLabel className="flex items-center gap-2">
            <Icon className="h-4 w-4 shrink-0" />
            <span>{label}</span>
          </FormLabel>
          <Select
            value={String(field.value)}
            onValueChange={(v) => field.onChange(parseInt(v, 10))}
          >
            <FormControl>
              <SelectTrigger
                data-testid={`edit-user-${fieldKey}`}
                className="w-full"
              >
                <SelectValue placeholder="Select" />
              </SelectTrigger>
            </FormControl>
            <SelectContent>
              {POSITION_OPTIONS.map(([value, text]) => (
                <SelectItem key={value} value={String(value)}>
                  {text}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <FormMessage />
        </FormItem>
      )}
    />
  );
}

function StringField({
  form,
  fieldKey,
  label,
}: {
  form: UseFormReturn<EditUserInput>;
  fieldKey: 'nickname';
  label: string;
}) {
  return (
    <FormField
      control={form.control}
      name={fieldKey}
      render={({ field }) => (
        <FormItem>
          <FormLabel>{label}</FormLabel>
          <FormControl>
            <Input
              ref={field.ref}
              name={field.name}
              onBlur={field.onBlur}
              value={field.value ?? ''}
              onChange={(e) =>
                field.onChange(e.target.value === '' ? null : e.target.value)
              }
              data-testid={`edit-user-${fieldKey}`}
            />
          </FormControl>
          <FormMessage />
        </FormItem>
      )}
    />
  );
}

function NumberField({
  form,
  fieldKey,
  label,
}: {
  form: UseFormReturn<EditUserInput>;
  fieldKey: 'mmr' | 'steam_account_id';
  label: string;
}) {
  return (
    <FormField
      control={form.control}
      name={fieldKey}
      render={({ field }) => (
        <FormItem>
          <FormLabel>{label}</FormLabel>
          <FormControl>
            <Input
              ref={field.ref}
              name={field.name}
              onBlur={field.onBlur}
              type="number"
              value={field.value ?? ''}
              onChange={(e) => {
                // Coerce to number on each keystroke so dirtyFields compares
                // numeric-to-numeric (defaultValues are numbers from buildDefaults).
                // Empty input → null (matches Zod's .nullable()).
                const raw = e.target.value;
                if (raw === '') {
                  field.onChange(null);
                } else {
                  const n = Number(raw);
                  field.onChange(Number.isFinite(n) ? n : raw);
                }
              }}
              data-testid={`edit-user-${fieldKey}`}
            />
          </FormControl>
          <FormMessage />
        </FormItem>
      )}
    />
  );
}

export const UserEditForm: React.FC<Props> = ({ form, showMmr, mmrLabel }) => {
  // No outer <ScrollArea> — FormDialog already wraps its children in one.
  return (
    <div className="flex flex-col w-full gap-4">
      <StringField form={form} fieldKey="nickname" label="Nickname" />
      {showMmr && (
        <NumberField form={form} fieldKey="mmr" label={mmrLabel} />
      )}
      <div className="bg-base-300 border border-border rounded-lg p-4">
        <h3 className="text-foreground text-center text-sm font-medium mb-3">
          Positions
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4">
          {positionKeys.map((key) => (
            <PositionSelect
              key={key}
              form={form}
              fieldKey={key}
              label={POSITION_LABELS[key]}
              Icon={positionIcons[key]}
            />
          ))}
        </div>
      </div>
      <NumberField
        form={form}
        fieldKey="steam_account_id"
        label="Friend ID"
      />
    </div>
  );
};
