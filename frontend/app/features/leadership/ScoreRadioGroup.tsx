import { RadioGroup, RadioGroupItem } from '~/components/ui/radio-group';
import { cn } from '~/lib/utils';
import { SCORE_VALUES } from './schemas';

export interface ScoreRadioGroupProps {
  name: string;
  label: string;
  value: number | undefined;
  onChange: (value: number) => void;
  disabled?: boolean;
  testIdPrefix: string;
  id?: string;
  'aria-describedby'?: string;
  'aria-invalid'?: boolean;
}

export function ScoreRadioGroup({
  name,
  label,
  value,
  onChange,
  disabled,
  testIdPrefix,
  id,
  'aria-describedby': describedBy,
  'aria-invalid': invalid,
}: ScoreRadioGroupProps) {
  return (
    <RadioGroup
      id={id}
      name={name}
      aria-label={label}
      aria-describedby={describedBy}
      aria-invalid={invalid}
      orientation="horizontal"
      value={value === undefined ? '' : String(value)}
      onValueChange={(v) => onChange(Number(v))}
      disabled={disabled}
      className="grid grid-cols-5 gap-2"
    >
      {SCORE_VALUES.map((n) => (
        <label
          key={n}
          data-testid={`${testIdPrefix}-${n}`}
          className={cn(
            'flex min-h-11 cursor-pointer items-center justify-center rounded-md border border-border bg-input/30 text-base font-semibold tabular-nums transition-colors sm:min-h-9',
            'hover:bg-accent focus-within:ring-2 focus-within:ring-inset focus-within:ring-ring',
            'has-[[data-state=checked]]:border-primary has-[[data-state=checked]]:bg-primary/15 has-[[data-state=checked]]:text-primary',
            disabled && 'cursor-not-allowed opacity-60 hover:bg-input/30',
          )}
        >
          <RadioGroupItem
            value={String(n)}
            aria-label={String(n)}
            className="sr-only"
          />
          <span aria-hidden="true">{n}</span>
        </label>
      ))}
    </RadioGroup>
  );
}
