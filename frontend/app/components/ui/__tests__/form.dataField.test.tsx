// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import { useForm } from 'react-hook-form';
import { describe, expect, it } from 'vitest';
import { Form, FormField, FormItem } from '../form';

function Harness() {
  const form = useForm({ defaultValues: { min_mmr: 0 } });
  return (
    <Form {...form}>
      <FormField
        control={form.control}
        name="min_mmr"
        render={() => <FormItem data-testid="item" />}
      />
    </Form>
  );
}

describe('FormItem', () => {
  it('tags itself with the name of its FormField', () => {
    render(<Harness />);
    expect(screen.getByTestId('item')).toHaveAttribute('data-field', 'min_mmr');
  });
});
