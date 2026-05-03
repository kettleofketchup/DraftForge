import * as React from 'react';
import { SelectContent, SelectItem } from '~/components/ui/select';
import {
  CarrySVG,
  HardSupportSVG,
  MidSVG,
  OfflaneSVG,
  SoftSupportSVG,
} from '~/components/user/positions/icons';

/** Per-role rating labels (0–5 scale used on the user edit form). */
export const PositionChoiceEnum: Record<number, string> = {
  0: "0: Don't show this role",
  1: '1: Favorite',
  2: '2: Can play',
  3: '3: If the team needs',
  4: '4: I would rather not',
  5: '5: Least Favorite',
};

/** Stable [value, label] pairs for rendering the rating select. */
export const POSITION_OPTIONS: Array<[number, string]> = (
  Object.entries(PositionChoiceEnum) as Array<[string, string]>
).map(([k, v]) => [Number(k), v]);

/** The five Dota role keys, in canonical 1-5 order. Canonical home — other
 *  modules (teamdraft, editForm, etc.) should import from here rather than
 *  redeclare. */
export type PositionKey =
  | 'carry'
  | 'mid'
  | 'offlane'
  | 'soft_support'
  | 'hard_support';

/** The five role keys in canonical order. */
export const positionKeys: PositionKey[] = [
  'carry',
  'mid',
  'offlane',
  'soft_support',
  'hard_support',
];

/** Display label per role. */
export const POSITION_LABELS: Record<PositionKey, string> = {
  carry: 'Carry',
  mid: 'Mid',
  offlane: 'Offlane',
  soft_support: 'Soft Support',
  hard_support: 'Hard Support',
};

/** Icon component per role. */
export const positionIcons: Record<PositionKey, React.FC<{ className?: string }>> = {
  carry: CarrySVG,
  mid: MidSVG,
  offlane: OfflaneSVG,
  soft_support: SoftSupportSVG,
  hard_support: HardSupportSVG,
};

export const positionChoices = () => {
  return (
    <SelectContent>
      <SelectItem value="0">{PositionChoiceEnum[0]}</SelectItem>
      <SelectItem value="1">{PositionChoiceEnum[1]}</SelectItem>
      <SelectItem value="2">{PositionChoiceEnum[2]}</SelectItem>
      <SelectItem value="3">{PositionChoiceEnum[3]}</SelectItem>
      <SelectItem value="4">{PositionChoiceEnum[4]}</SelectItem>
      <SelectItem value="5">{PositionChoiceEnum[5]}</SelectItem>
    </SelectContent>
  );
};
