import { getLogger } from '~/lib/logger';

const log = getLogger('AboutHero');

export function AboutHero() {
  log.debug('Rendering AboutHero component');

  return (
    <div className="hero bg-gradient-to-br from-primary/10 to-secondary/10 py-20">
      <div className="hero-content text-center">
        <div className="max-w-4xl">
          <h1 className="text-6xl font-bold text-primary mb-6">About DTX</h1>
          <p className="text-xl text-base-content/80 mb-8">
            Your premier Dota 2 Guild/Discord Community
          </p>
        </div>
      </div>
    </div>
  );
}
