import { motion } from 'framer-motion';
import type { FormEvent } from 'react';
import React, { useEffect, useState } from 'react';
import type { TeamType } from '~/components/tournament/types';
import { getLogger } from '~/lib/logger';
import { useUserStore } from '~/store/userStore';
import type { UserType } from '../user/types';
import TeamEditModal from './teamCard/editModal';
import { TeamTable } from './teamTable/teamTable';
const log = getLogger('teamCard');

interface Props {
  team: TeamType;
  edit?: boolean;
  saveFunc?: string;
  compact?: boolean;
  removeCallBack?: (e: FormEvent, user: UserType) => void;
  removeToolTip?: string;
}
export const TeamCard: React.FC<Props> = ({
  team,
  edit,
  saveFunc,
  compact,
  removeCallBack,
  removeToolTip = 'Delete the user',
}) => {
  const [editMode, setEditMode] = useState(edit || false);

  const currentUser: UserType = useUserStore((state) => state.currentUser); // Zustand setter

  useEffect(() => {
    if (team) {
      log.debug(`UserCard: user updated ${team.name}`);
    }
  }, [team.pk, team.captain?.pk, team.members?.length, team.draft_order]);

  const getAverageMMR = () => {
    if (!team.members || team.members.length === 0) return 'N/A';
    const totalMMR = team.members.reduce((acc, member) => {
      return acc + (member.mmr || 0);
    }, 0);
    return (totalMMR / team.members.length).toFixed(2);
  };
  const teamHeader = () => {
    return (
      <>
        {!editMode && (
          <div className="flex-1 justify-between text-center">
            <h2 className="card-title text-lg">{team.name}</h2>

            <h3 className="card-title text-lg">Avg MMR: {getAverageMMR()}</h3>
          </div>
        )}
      </>
    );
  };
  const showTeamMembers = () => {
    if (!team.members || team.members.length === 0) return <></>;
    return (
      <div className="flex items-center gap-2 w-full">
        <TeamTable team={team} />
      </div>
    );
  };

  const viewMode = () => {
    if (compact) {
      return <>{team.members && showTeamMembers()}</>;
    }
    return <>{team.members && showTeamMembers()}</>;
  };

  const getKeyName = () => {
    let result = '';
    if (team.pk) {
      result += team.pk.toString();
    }
    if (team.name) {
      result += team.name;
    }
    return result;
  };
  return (
    <div
      key={`teamCard:${getKeyName()} base`}
      className="flex 002items-center [content-visibility: auto] [contain-intrinsic-size: 400px 220px] px-6 py-4 content-center justify-center
      content-center"
    >
      <motion.div
        initial={{ opacity: 0 }}
        exit={{ opacity: 0 }}
        whileInView={{
          opacity: 1,
          transition: { delay: 0.05, duration: 0.5 },
        }}
        whileHover={{ scale: 1.02 }}
        whileFocus={{ scale: 1.05 }}
        key={`usercard:${getKeyName()} basediv`}
        className="flex-1 flex-grow
        justify-between p-2 h-full card bg-base-200 shadow-md w-full
            max-w-sm hover:bg-violet-900 . focus:outline-2
            hover:shadow-xl/30
            focus:outline-offset-2 focus:outline-violet-500
            focus:outline-offset-2 active:bg-violet-900 min-w-fit"
      >
        <div className="flex items-center gap-2 items-center justify-center flex-grow">
          {teamHeader()}
          {(currentUser.is_staff || currentUser.is_superuser) &&
            saveFunc === 'save' &&
            !compact && <TeamEditModal team={team} />}
        </div>

        <div className="flex mt-2 space-y-2 text-sm flex-grow">
          {viewMode()}
          <div className="flex flex-col "></div>
        </div>
      </motion.div>
    </div>
  );
};
