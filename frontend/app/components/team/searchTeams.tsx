import { Combobox, ComboboxInput } from '@headlessui/react';
import React from 'react';
import type { TeamType } from '~/components/tournament/types';
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
    <div className="justify-self-top content-self-center align-middle ">
      {teams && (
        <Combobox value={query}>
          <ComboboxInput
            className="input input-bordered w-full"
            placeholder="Search by team name or member"
            onChange={(event) => setQuery(event.target.value)}
            onClick={(event) => console.log(event.target)}
          />
        </Combobox>
      )}
    </div>
  );
};
