// @vitest-environment jsdom
import { fireEvent, render, screen } from '@testing-library/react';
import { useForm, type UseFormReturn } from 'react-hook-form';
import { beforeAll, describe, expect, it } from 'vitest';

import { Form } from '~/components/ui/form';
import { DraftTypeField } from '../DraftTypeField';
import { DRAFT_STYLE_LABELS, DRAFT_STYLE_VALUES } from '../schemas';

beforeAll(() => {
  Element.prototype.hasPointerCapture ??= () => false;
  Element.prototype.releasePointerCapture ??= () => undefined;
  Element.prototype.scrollIntoView ??= () => undefined;
});

type Fields = { draft_type: string };
type FieldProps = Omit<Parameters<typeof DraftTypeField<Fields>>[0], 'control'>;

let form: UseFormReturn<Fields>;

function Harness({ draftType, ...props }: FieldProps & { draftType: string }) {
  form = useForm<Fields>({ defaultValues: { draft_type: draftType } });
  return (
    <Form {...form}>
      <DraftTypeField control={form.control} {...props} />
    </Form>
  );
}

function renderField(draftType = 'shuffle', props: FieldProps = {}) {
  render(<Harness draftType={draftType} {...props} />);
}

const trigger = (name = 'Draft Type') => screen.getByRole('combobox', { name });

function openSelect(name?: string) {
  fireEvent.pointerDown(trigger(name), {
    button: 0,
    ctrlKey: false,
    pointerType: 'mouse',
  });
}

describe('DraftTypeField', () => {
  it.each(DRAFT_STYLE_VALUES)('shows the label for %s', (value) => {
    renderField(value);
    expect(trigger()).toHaveTextContent(DRAFT_STYLE_LABELS[value]);
  });

  it('lists the three draft types in order', () => {
    renderField();
    openSelect();
    expect(screen.getAllByRole('option').map((o) => o.textContent)).toEqual([
      'Shuffle — MMR point buy draft',
      'Snake Draft — Captains pick in snake order',
      'Manual — Manually assign players',
    ]);
  });

  it('writes the draft type value, not its label, to the form', () => {
    renderField('shuffle');
    openSelect();
    fireEvent.click(
      screen.getByRole('option', { name: DRAFT_STYLE_LABELS.normal }),
    );
    expect(form.getValues('draft_type')).toBe('normal');
    expect(trigger()).toHaveTextContent(DRAFT_STYLE_LABELS.normal);

    openSelect();
    fireEvent.click(
      screen.getByRole('option', { name: DRAFT_STYLE_LABELS.snake }),
    );
    expect(form.getValues('draft_type')).toBe('snake');
  });

  it('has no description or test ids by default', () => {
    renderField();
    expect(trigger()).not.toHaveAttribute('data-testid');
    expect(trigger()).not.toHaveAccessibleDescription();
    openSelect();
    for (const option of screen.getAllByRole('option')) {
      expect(option).not.toHaveAttribute('data-testid');
    }
  });

  it('applies the label, description and test id props', () => {
    renderField('snake', {
      label: 'Draft type',
      description: 'How captains build teams',
      testId: 'event-draft-type',
    });
    const t = trigger('Draft type');
    expect(t).toHaveAttribute('data-testid', 'event-draft-type');
    expect(t).toHaveAccessibleDescription('How captains build teams');

    openSelect('Draft type');
    for (const value of DRAFT_STYLE_VALUES) {
      expect(screen.getByTestId(`event-draft-type-${value}`)).toHaveTextContent(
        DRAFT_STYLE_LABELS[value],
      );
    }
    fireEvent.click(screen.getByTestId('event-draft-type-shuffle'));
    expect(form.getValues('draft_type')).toBe('shuffle');
  });
});
