// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { useForm } from 'react-hook-form';
import { afterEach, describe, expect, it } from 'vitest';

import { Form } from '~/components/ui/form';

import {
  NumberSetting,
  SettingsGroup,
  ToggleSetting,
} from '~/components/organization/tabs/orgSettings/settingFields';

type Values = { a: number; on: boolean; nested: { b: number } };

function Harness({ initial }: { initial: Values }) {
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
      </SettingsGroup>
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
});
