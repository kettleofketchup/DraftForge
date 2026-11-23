// @vitest-environment jsdom
import { fireEvent, render, screen } from '@testing-library/react';
import { useForm, type UseFormReturn } from 'react-hook-form';
import { describe, expect, it } from 'vitest';
import { Form } from '~/components/ui/form';
import {
  TeamSizeFields,
  type TeamSizeFieldValues,
} from '../form/fields/TeamSizeFields';

const testIds = {
  peoplePerTeam: 'ppt',
  maxTeams: 'max-teams',
  unlimited: 'unlimited',
};

let form: UseFormReturn<TeamSizeFieldValues>;

function Harness() {
  form = useForm<TeamSizeFieldValues>({
    defaultValues: { people_per_team: 5, number_of_teams: 20 },
  });
  return (
    <Form {...form}>
      <TeamSizeFields control={form.control} testIds={testIds} />
    </Form>
  );
}

const el = (id: string) => screen.getByTestId(id) as HTMLInputElement;
const type = (id: string, value: string) =>
  fireEvent.change(el(id), { target: { value } });

describe('TeamSizeFields', () => {
  it('clearing Max Teams does not switch to Unlimited', () => {
    render(<Harness />);
    type('max-teams', '');
    expect(el('unlimited').checked).toBe(false);
    expect(el('max-teams').disabled).toBe(false);
    type('max-teams', '1');
    type('max-teams', '16');
    expect(el('max-teams').value).toBe('16');
    expect(form.getValues('number_of_teams')).toBe(16);
  });

  it('clearing People Per Team lets a new value be typed', () => {
    render(<Harness />);
    type('ppt', '');
    expect(el('ppt').value).toBe('');
    type('ppt', '3');
    expect(el('ppt').value).toBe('3');
    expect(form.getValues('people_per_team')).toBe(3);
  });

  it('Unlimited still toggles the limit off and on', () => {
    render(<Harness />);
    fireEvent.click(el('unlimited'));
    expect(form.getValues('number_of_teams')).toBeNull();
    expect(el('max-teams').disabled).toBe(true);
    fireEvent.click(el('unlimited'));
    expect(form.getValues('number_of_teams')).toBe(2);
    expect(el('max-teams').value).toBe('2');
  });
});
