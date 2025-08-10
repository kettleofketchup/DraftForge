import { useEffect } from 'react';
import { getLogger } from '~/lib/logger';
import { useUserStore } from '~/store/userStore';

const log = getLogger('AboutHero');
export function AboutHero() {
  log.debug('Rendering AboutHero component');
  const getDiscordUsers = useUserStore((state) => state.getDiscordUsers);
  const discordUsers = useUserStore((state) => state.discordUsers);

  useEffect(() => {
    if (discordUsers.length === 0) getDiscordUsers();
  }, []);

  return (
    <div className="hero bg-gradient-to-br from-primary/10 to-secondary/10 py-20">
      <div className="hero-content text-center">
        <div className="max-w-4xl">
          <h1 className="text-6xl font-bold text-primary mb-6">About DTX</h1>
          <p className="text-xl text-base-content/80 mb-8">
            Your premier Dota 2 Guild/Discord Community
          </p>
          <p className="text-lg text-base-content">
            <span className="font-bold animate-pulse">
              {discordUsers.length}
            </span>{' '}
            Members
            <span className="font-bold"> Strong</span>
          </p>
        </div>
      </div>
    </div>
  );
}
