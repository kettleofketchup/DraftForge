import { Combobox, ComboboxInput } from '@headlessui/react';
import React from 'react';
import type { TeamType } from '~/components/tournament/types';
import { Input } from '~/components/ui/input';
import { getLogger } from '~/lib/logger';

const log = getLogger('searchTeams');
interface Props {
  teams: TeamType[];
  query: string;
  setQuery: React.Dispatch<React.SetStateAction<string>>;
}
export const SearchTeamsDropdown: React.FC<Props> = ({
  teams,
  query,
  setQuery,
}) => {
  return (
    <div className="align-middle">
      {teams && (
        <Combobox value={query}>
          <ComboboxInput
            as={Input}
            placeholder="Search by team name or member"
            onChange={(event) => setQuery(event.target.value)}
            onClick={(event) => log.debug(event.target)}
          />
        </Combobox>
      )}
    </div>
  );
};
