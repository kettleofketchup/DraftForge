// @vitest-environment jsdom
import { fireEvent, render, screen } from '@testing-library/react';
import { useForm, type UseFormReturn } from 'react-hook-form';
import { beforeAll, describe, expect, it } from 'vitest';

import { Form } from '~/components/ui/form';
import {
  EVENT_TIMEZONES,
  formatTimezoneLabel,
  TOURNAMENT_TIMEZONES,
} from '~/lib/timezones';
import { TimezoneField } from '../fields/TimezoneField';

beforeAll(() => {
  Element.prototype.hasPointerCapture ??= () => false;
  Element.prototype.releasePointerCapture ??= () => undefined;
  Element.prototype.scrollIntoView ??= () => undefined;
});

type Fields = { timezone: string };
type FieldProps = Omit<Parameters<typeof TimezoneField<Fields>>[0], 'control'>;

let form: UseFormReturn<Fields>;

function Harness({ timezone, ...props }: FieldProps & { timezone: string }) {
  form = useForm<Fields>({ defaultValues: { timezone } });
  return (
    <Form {...form}>
      <TimezoneField control={form.control} {...props} />
    </Form>
  );
}

function renderField(timezone = 'America/New_York', props: FieldProps = {}) {
  render(<Harness timezone={timezone} {...props} />);
}

const trigger = (name = 'Timezone') => screen.getByRole('combobox', { name });

function openSelect(name?: string) {
  fireEvent.pointerDown(trigger(name), {
    button: 0,
    ctrlKey: false,
    pointerType: 'mouse',
  });
}

const optionNames = () =>
  screen.getAllByRole('option').map((o) => o.textContent);

describe('TimezoneField', () => {
  it('shows the form value with underscores replaced by spaces', () => {
    renderField('America/Los_Angeles');
    expect(trigger()).toHaveTextContent('America/Los Angeles');
  });

  it('shows the placeholder when the form has no timezone', () => {
    renderField('');
    expect(trigger()).toHaveTextContent('Select timezone');
  });

  it('lists every event timezone by default', () => {
    renderField();
    openSelect();
    expect(optionNames()).toEqual(EVENT_TIMEZONES.map(formatTimezoneLabel));
  });

  it('writes the raw IANA name to the form when an option is picked', () => {
    renderField();
    openSelect();
    fireEvent.click(screen.getByRole('option', { name: 'Asia/Kolkata' }));
    expect(form.getValues('timezone')).toBe('Asia/Kolkata');
    expect(trigger()).toHaveTextContent('Asia/Kolkata');

    openSelect();
    fireEvent.click(screen.getByRole('option', { name: 'America/Sao Paulo' }));
    expect(form.getValues('timezone')).toBe('America/Sao_Paulo');
  });

  it('uses a custom timezone list and label formatter', () => {
    renderField('UTC', {
      timezones: TOURNAMENT_TIMEZONES,
      formatLabel: (tz) => `tz:${tz}`,
    });
    expect(trigger()).toHaveTextContent('tz:UTC');
    openSelect();
    expect(optionNames()).toEqual(TOURNAMENT_TIMEZONES.map((tz) => `tz:${tz}`));
    fireEvent.click(screen.getByRole('option', { name: 'tz:Europe/Berlin' }));
    expect(form.getValues('timezone')).toBe('Europe/Berlin');
  });

  it('renders the default label without icon, description or test ids', () => {
    renderField();
    const label = screen.getByText('Timezone');
    expect(label.querySelector('svg')).toBeNull();
    expect(trigger()).not.toHaveAttribute('data-testid');
    expect(trigger()).not.toHaveAccessibleDescription();
    openSelect();
    expect(
      screen
        .getAllByRole('option')
        .filter((o) => o.hasAttribute('data-testid')),
    ).toHaveLength(0);
  });

  it('applies the label, icon, description and test id props', () => {
    renderField('UTC', {
      label: 'Event timezone',
      description: 'Inherited from org defaults',
      showIcon: true,
      triggerTestId: 'tz-trigger',
      itemTestIdPrefix: 'tz-',
    });
    const t = trigger('Event timezone');
    expect(t).toHaveAttribute('data-testid', 'tz-trigger');
    expect(t).toHaveAccessibleDescription('Inherited from org defaults');
    expect(
      screen.getByText('Event timezone').querySelector('svg'),
    ).toBeInTheDocument();

    openSelect('Event timezone');
    fireEvent.click(screen.getByTestId('tz-Europe/London'));
    expect(form.getValues('timezone')).toBe('Europe/London');
  });
});
