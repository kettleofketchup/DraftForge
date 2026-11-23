import * as React from 'react';

import { Input } from '~/components/ui/input';

type IntegerInputProps = Omit<
  React.ComponentProps<typeof Input>,
  'type' | 'value' | 'onChange' | 'min'
> & {
  value: number | null | undefined;
  onValueChange: (value: number | null) => void;
  min?: number;
  /** Empty means null (e.g. "no limit"); otherwise empty reverts on blur. */
  nullable?: boolean;
};

const toText = (v: number | null | undefined): string =>
  v == null || Number.isNaN(v) ? '' : String(v);

/**
 * Number input that keeps what the user is typing. Empty or below-min text
 * never reaches the form mid-edit; it is resolved on blur instead.
 */
export function IntegerInput({
  value,
  onValueChange,
  min,
  nullable = false,
  onBlur,
  ...props
}: IntegerInputProps) {
  const [text, setText] = React.useState(() => toText(value));
  const [shown, setShown] = React.useState(value);
  if (!Object.is(value, shown)) {
    setShown(value);
    setText(toText(value));
  }

  return (
    <Input
      {...props}
      type="number"
      inputMode="numeric"
      min={min}
      value={text}
      onChange={(e) => {
        const raw = e.target.value;
        setText(raw);
        if (raw.trim() === '') {
          if (nullable) onValueChange(null);
          return;
        }
        const n = parseInt(raw, 10);
        if (!Number.isNaN(n) && (min == null || n >= min)) onValueChange(n);
      }}
      onBlur={(e) => {
        const n = parseInt(text, 10);
        const next = Number.isNaN(n)
          ? nullable
            ? null
            : (value ?? null)
          : Math.max(min ?? n, n);
        if (!Object.is(next, value ?? null)) onValueChange(next);
        setText(toText(next));
        onBlur?.(e);
      }}
    />
  );
}
