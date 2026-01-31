import { Beer, Binary, Code, Gamepad2, HeartPlus } from 'lucide-react';
import { Badge } from '~/components/ui/badge';
import { Button } from '~/components/ui/button';
import { UserAvatar } from '~/components/user/UserAvatar';
import { getLogger } from '~/lib/logger';
import { useUserStore } from '~/store/userStore';

import {
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '~/components/ui/tooltip';
const log = getLogger('MaintainerSection');

import { Tooltip } from '@radix-ui/react-tooltip';
import { motion } from 'framer-motion';
import { useEffect } from 'react';
export function MaintainerSection() {
  log.debug('Rendering MaintainerSection component');
  const users = useUserStore((state) => state.users);
  const getUsers = useUserStore((state) => state.getUsers);
  const getKettle = () =>
    users.find((user) => user.username === 'kettleofketchup');
  useEffect(() => {
    if (!getKettle()) {
      getUsers();
    }
  }, []);

  const buymeabeerContent = () => {
    'https://buymeabeer.com/kettleofketchup';

    return (
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger className="" asChild>
            <a
              className="flex justify-center mt-4 mb-2"
              href="https://buymeabeer.com/kettleofketchup"
              target="_blank"
              rel="noopener noreferrer"
            >
              <Button>
                <Beer className="h-16 w-16 hover:animate-spin" /> Buy me a beer
              </Button>
            </a>
          </TooltipTrigger>
          <TooltipContent>
            Server costs are covered by the community. Your support helps keep
            the site running!
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    );
  };
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 0.9 }}
      transition={{ duration: 0.2 }}
      exit={{ opacity: 0 }}
      whileHover={{ scale: 1.01 }}
      whileFocus={{ scale: 1.01 }}
    >
      <div className="card bg-base-200/50 backdrop-blur border border-primary/10 hover:border-primary/30 transition-all duration-300">
        <div className="card-body">
          <div className="flex items-center gap-4 mb-6">
            <div className="hover:animate-spin">
              <UserAvatar user={getKettle()} size="xl" />
            </div>
            <div>
              <h2 className="card-title text-2xl text-red-500">
                KettleOfKetchup
              </h2>
              <p className="text-base-content/70">Site Owner & Developer</p>
            </div>
          </div>

          <div className="bg-base-content/5 rounded-lg p-6 border border-base-content/10">
            <h3 className="text-xl font-semibold text-red-600 mb-3">
              About Me
            </h3>
            <p className="text-base-content mb-4">
              The driving force behind this website, KettleOfKetchup is
              responsible for maintaining, developing, and continuously
              improving this tournament and guild management system. With a passion for both
              Dota 2 and software development, they ensure that DraftForge remains a
              cutting-edge solution for gaming communities.
            </p>
            <div className="flex flex-wrap gap-2">
              <Badge className="bg-indigo-800 text-white">
                <Code />
                Software Developer
              </Badge>
              <Badge className="bg-red-800 text-white">
                <Binary />
                Exploitation Dev
              </Badge>
              <Badge variant="secondary">
                <Gamepad2 /> Dota 2 Enthusiast
              </Badge>
              <Badge className="bg-blue-800 text-white">
                <HeartPlus />
                Community Supporter
              </Badge>
            </div>
          </div>
        </div>

        <div className="flex flex-col">
          <span className="text-sm text-base-content/70 text-center mt-2">
            If you appreciate the work done on this site and would like to
            support, you can do so anonymously using buymeabeer.com which uses
            stripe in the backend.
          </span>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.2 }}
            exit={{ opacity: 0 }}
            whileHover={{ scale: 1.05 }}
            whileFocus={{ scale: 1.05 }}
          >
            {buymeabeerContent()}
          </motion.div>
        </div>
      </div>
    </motion.div>
  );
}
