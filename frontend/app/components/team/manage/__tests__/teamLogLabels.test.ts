import { describe, expect, it } from 'vitest';
import { teamLogActionLabel, teamLogViaLabel } from '../teamLogLabels';

describe('teamLogActionLabel', () => {
  it.each([
    ['set_captain', 'Set captain'],
    ['set_deputy', 'Set deputy'],
    ['mark_dropout', 'Marked dropout'],
    ['restore_member', 'Restored'],
    ['add_standin', 'Added stand-in'],
    ['remove_standin', 'Removed stand-in'],
    ['sub_in', 'Subbed in'],
    ['rename', 'Renamed'],
    ['legacy_patch', 'Edited (legacy)'],
    ['system_succession', 'Automatic captain succession'],
    ['empty_team_kept', 'Empty team kept'],
    ['team_deleted', 'Team deleted'],
    ['materialize', 'Materialized'],
    ['replace_captain', 'Replace captain'],
    ['set_placement', 'Set placement'],
  ])('%s -> %s', (action, label) => {
    expect(teamLogActionLabel(action)).toBe(label);
  });

  it('falls back to the raw value', () => {
    expect(teamLogActionLabel('brand_new')).toBe('brand_new');
  });
});

describe('teamLogViaLabel', () => {
  it.each([
    ['web', 'Web'],
    ['discord', 'Discord'],
    ['api', 'API'],
    ['system', 'System'],
  ])('%s -> %s', (via, label) => {
    expect(teamLogViaLabel(via)).toBe(label);
  });

  it('falls back to the raw value', () => {
    expect(teamLogViaLabel('carrier_pigeon')).toBe('carrier_pigeon');
  });
});
