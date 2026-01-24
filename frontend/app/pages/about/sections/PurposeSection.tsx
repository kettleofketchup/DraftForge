import { motion } from 'framer-motion';
import { useEffect } from 'react';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '~/components/ui/tooltip';
import { AvatarUrl } from '~/components/user/avatar';
import { getLogger } from '~/lib/logger';
import { useUserStore } from '~/store/userStore';

const log = getLogger('PurposeSection');
export function PurposeSection() {
  log.debug('Rendering PurposeSection component');
  const users = useUserStore((state) => state.users);
  const getDiscordUsers = useUserStore((state) => state.getDiscordUsers);
  const discordUsers = useUserStore((state) => state.discordUsers);
  const getUsers = useUserStore((state) => state.getUsers);
  const getHurk = () => users.find((user) => user.username === 'hurk_');

  const memberCount =
    discordUsers.length === 0 ? 'Loading ...' : String(discordUsers.length);
  useEffect(() => {
    if (!getHurk()) getUsers();
    if (discordUsers.length === 0) getDiscordUsers();
  }, []);

  const hurkIcon = () => {
    return (
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger className="flex justify-center mt-4 mb-2" asChild>
            <img
              src={AvatarUrl(getHurk())}
              alt="Hurk's avatar"
              className="w-8 h-8 rounded-full"
            />
          </TooltipTrigger>
          <TooltipContent>Hurk is the founder of DTX</TooltipContent>
        </Tooltip>
      </TooltipProvider>
    );
  };

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.5, delay: 0.1 }}
      whileHover={{
        scale: 1.05,
        transition: {
          delay: 0,
          duration: 0.2,
        },
      }}
    >
      <div className="card bg-base-200/50 backdrop-blur border border-primary/10 mb-12">
        <div className="card-body">
          <h2 className="card-title text-3xl text-primary mb-6">
            <div className="flex flex-row items-center gap-2">
              {hurkIcon()}
              <h3 className="text-lg font-semibold">Our Purpose</h3>
            </div>
          </h2>
          <div className="prose max-w-none">
            <p className="text-lg text-base-content mb-4">
              DTX is a competitive, community‑driven Dota 2 guild ranked #1 on
              US EAST for the past 2 years. We have{' '}
              <span className="font-bold animate-pulse">{memberCount}</span>{' '}
              members and are focused on teamwork, community, and consistent
              improvement. This site supports DTX operations— coordinating
              rosters and scrims, publishing schedules, tracking match stats,
              and keeping everyone aligned through Discord integration. Whether
              you’re grinding ranked, scrimming, or preparing for leagues, DTX
              members can find tools, resources, and updates here to play
              smarter together.
            </p>
            <p className="text-base-content">
              This site is dedicated to providing a comprehensive management
              solution for our Dota 2 gaming organization. This platform serves
              as the central hub for all guild-related activities, offering
              tools and features that enhance our community experience.
            </p>
          </div>
        </div>
      </div>
    </motion.div>
  );
}
