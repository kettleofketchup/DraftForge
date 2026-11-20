// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import { StrictMode } from 'react';
import { Controller, useForm } from 'react-hook-form';
import { describe, expect, it, vi } from 'vitest';

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '~/components/ui/select';

type Values = { tz: string };

function Harness({
  initial,
  onState,
}: {
  initial: string;
  onState: (v: string, dirty: boolean) => void;
}) {
  const { control, reset, watch, formState } = useForm<Values>({
    defaultValues: { tz: 'a' },
  });
  onState(watch('tz'), formState.isDirty);
  return (
    <form>
      <Controller
        control={control}
        name="tz"
        render={({ field }) => (
          <Select value={field.value} onValueChange={field.onChange}>
            <SelectTrigger aria-label="tz">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="a">A</SelectItem>
              <SelectItem value="b">B</SelectItem>
            </SelectContent>
          </Select>
        )}
      />
      <button type="button" onClick={() => reset({ tz: initial })}>
        load
      </button>
    </form>
  );
}

describe('Select with a value that has no option', () => {
  it('does not clobber the form value or mark it dirty', async () => {
    const onState = vi.fn();
    render(
      <StrictMode>
        <Harness initial="gone" onState={onState} />
      </StrictMode>,
    );
    screen.getByText('load').click();
    await new Promise((r) => setTimeout(r, 50));
    const [value, dirty] = onState.mock.calls.at(-1)!;
    expect(value).toBe('gone');
    expect(dirty).toBe(false);
  });
});
