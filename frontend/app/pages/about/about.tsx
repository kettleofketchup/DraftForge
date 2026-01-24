import { AboutHero } from '~/pages/about/sections/AboutHero';
import { FeaturesSection } from '~/pages/about/sections/FeaturesSection';
import { HistorySection } from '~/pages/about/sections/HistorySection';
import { MaintainerSection } from '~/pages/about/sections/MaintainerSection';
import { TechnologyStack } from '~/pages/about/sections/TechnologyStack';
import { getLogger } from '~/lib/logger';

const log = getLogger('About');

export function About() {
  log.info('Rendering About page');

  return (
    <div className="min-h-screen">
      <AboutHero />

      <div className="container mx-auto px-6 py-16 max-w-4xl">
        <MaintainerSection />
        <HistorySection />
        <FeaturesSection />
        <TechnologyStack />
      </div>
    </div>
  );
}
