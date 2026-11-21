import { describe, expect, it } from 'vitest';
import { ConductSettingsFormSchema } from '../schemas';
import {
  CONDUCT_SETTINGS_FIELDS,
  conductSettingsFieldErrors,
  pickConductFormValues,
} from '../settingsForm';
import { conductSettings, conductSettingsValues } from './fixtures';

describe('conduct settings form helpers', () => {
  it('lists exactly the form fields', () => {
    expect([...CONDUCT_SETTINGS_FIELDS].sort()).toEqual(
      Object.keys(ConductSettingsFormSchema.shape).sort(),
    );
  });

  it('picks form values and drops the defaults', () => {
    expect(pickConductFormValues(conductSettings({ min_events: 5 }))).toEqual(
      conductSettingsValues({ min_events: 5 }),
    );
  });

  it('keeps DRF errors that name a settings field', () => {
    const err = {
      response: {
        data: {
          block_below: ['Must be below require_approval_below.'],
          min_events: 'Too high.',
          detail: 'ignored',
          unknown_field: ['ignored'],
        },
      },
    };
    expect(conductSettingsFieldErrors(err)).toEqual([
      ['block_below', 'Must be below require_approval_below.'],
      ['min_events', 'Too high.'],
    ]);
    expect(conductSettingsFieldErrors(new Error('network'))).toEqual([]);
  });
});
