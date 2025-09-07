import { SelectContent, SelectItem } from '~/components/ui/select';
import { getLogger } from '~/lib/logger';
const log = getLogger('Position Edit');

export const PositionChoiceEnum: Record<number, string> = {
  0: "0: Don't show this role",
  1: '1: Favorite',
  2: '2: Can play',
  3: '3: If the team needs',
  4: '4: I would rather not but I guess',
  5: '5: Least Favorite',
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
