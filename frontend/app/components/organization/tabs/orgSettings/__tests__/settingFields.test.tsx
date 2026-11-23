// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { useForm } from 'react-hook-form';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { Form } from '~/components/ui/form';

import {
  NumberSetting,
  SettingsGroup,
  ToggleSetting,
} from '~/components/organization/tabs/orgSettings/settingFields';

type Values = {
  a: number;
  on: boolean;
  nested: { b: number };
  h?: number | null;
};

function Harness({
  initial,
  hoursDisabled = false,
  onSubmit,
}: {
  initial: Values;
  hoursDisabled?: boolean;
  onSubmit?: (values: Values) => void;
}) {
  const form = useForm<Values>({ defaultValues: initial });
  const common = { control: form.control, setValue: form.setValue };
  return (
    <Form {...form}>
      <SettingsGroup title="Group">
        <NumberSetting
          {...common}
          name="a"
          label="A"
          help="Help for A"
          step={1}
          defaultValue={5}
          testIdPrefix="x"
        />
        <NumberSetting
          {...common}
          name="nested.b"
          label="B"
          help="Help for B"
          step={0.5}
          defaultValue={2}
          testIdPrefix="x"
        />
        <ToggleSetting
          {...common}
          name="on"
          label="On"
          help="Help for on"
          defaultValue={false}
          testIdPrefix="x"
        />
        <NumberSetting
          {...common}
          name="h"
          label="Hours"
          help="Help for hours"
          step={1}
          defaultValue={null}
          testIdPrefix="x"
          nullable
          disabled={hoursDisabled}
        />
      </SettingsGroup>
      <button
        type="button"
        data-testid="submit"
        onClick={() => onSubmit?.(form.getValues())}
      />
    </Form>
  );
}

describe('settingFields', () => {
  afterEach(cleanup);

  it('shows Default and resets to it', () => {
    render(<Harness initial={{ a: 7, on: false, nested: { b: 2 } }} />);
    const input = screen.getByTestId<HTMLInputElement>('x-a');
    expect(input.value).toBe('7');
    expect(screen.queryByTestId('x-a-default')).toBeNull();
    expect(screen.getByTestId('x-on-default')).toBeInTheDocument();
    expect(screen.getByTestId('x-on-reset')).toBeDisabled();

    fireEvent.click(screen.getByTestId('x-a-reset'));

    expect(input.value).toBe('5');
    expect(screen.getByTestId('x-a-default')).toBeInTheDocument();
    expect(screen.getByTestId('x-a-reset')).toBeDisabled();
  });

  it('maps a nested name to a dashed testid', () => {
    render(<Harness initial={{ a: 5, on: true, nested: { b: 3 } }} />);
    expect(screen.getByTestId<HTMLInputElement>('x-nested-b').value).toBe('3');
    fireEvent.click(screen.getByTestId('x-nested-b-reset'));
    expect(screen.getByTestId<HTMLInputElement>('x-nested-b').value).toBe('2');
    expect(screen.getByTestId('x-nested-b-default')).toBeInTheDocument();
  });

  it('empties the input instead of showing NaN', () => {
    render(<Harness initial={{ a: 5, on: false, nested: { b: 2 } }} />);
    const input = screen.getByTestId<HTMLInputElement>('x-a');
    fireEvent.change(input, { target: { value: '' } });
    expect(input.value).toBe('');
    expect(screen.queryByTestId('x-a-default')).toBeNull();
  });

  it('maps a cleared nullable input to null, never NaN', () => {
    const onSubmit = vi.fn();
    render(
      <Harness
        initial={{ a: 5, on: false, nested: { b: 2 }, h: 48 }}
        onSubmit={onSubmit}
      />,
    );
    const input = screen.getByTestId<HTMLInputElement>('x-h');
    expect(input.value).toBe('48');
    fireEvent.change(input, { target: { value: '' } });
    expect(input.value).toBe('');
    expect(screen.getByTestId('x-h-default')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('submit'));
    expect(onSubmit.mock.calls[0][0].h).toBeNull();
    fireEvent.change(input, { target: { value: '24' } });
    fireEvent.click(screen.getByTestId('submit'));
    expect(onSubmit.mock.calls[1][0].h).toBe(24);
  });

  it('disables a nullable input and its reset', () => {
    render(
      <Harness
        initial={{ a: 5, on: false, nested: { b: 2 }, h: 48 }}
        hoursDisabled
      />,
    );
    expect(screen.getByTestId('x-h')).toBeDisabled();
    expect(screen.getByTestId('x-h-reset')).toBeDisabled();
  });
});
