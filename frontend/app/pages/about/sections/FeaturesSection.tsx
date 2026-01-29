import { Award, GitBranch, Shield, Swords, Trophy, Users } from 'lucide-react';
import { getLogger } from '~/lib/logger';
import { FeatureCard } from '~/components/feature/FeatureCard';

const log = getLogger('FeaturesSection');

// Video/GIF assets (mounted at public/assets/docs in dev, copied during build)
const ASSETS_BASE = '/assets/docs';

export function FeaturesSection() {
  log.debug('Rendering FeaturesSection component');

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold text-primary mb-6">Features</h2>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        <FeatureCard
          icon={Swords}
          title="Hero Draft System"
          description="Real-time captain's mode drafting with spectator view, timers, and pick/ban tracking. Perfect for competitive matches."
          delay={0.1}
          gifSrc={`${ASSETS_BASE}/gifs/captain1_herodraft.gif`}
          modalMedia={[
            { src: `${ASSETS_BASE}/videos/captain1_herodraft.webm`, caption: 'Captain 1 Perspective', type: 'video' },
            { src: `${ASSETS_BASE}/videos/captain2_herodraft.webm`, caption: 'Captain 2 Perspective', type: 'video' },
          ]}
          docsPath="/features/herodraft/"
          action={{ label: 'View Tournaments', href: '/tournaments' }}
        />
        <FeatureCard
          icon={GitBranch}
          title="Team Draft Composition"
          description="Draft 40+ team members in minutes with Snake, Normal, and Shuffle draft modes balanced by MMR."
          delay={0.2}
          gifSrc={`${ASSETS_BASE}/gifs/snake_draft.gif`}
          modalMedia={[
            { src: `${ASSETS_BASE}/videos/snake_draft.webm`, caption: 'Snake Draft', type: 'video' },
            { src: `${ASSETS_BASE}/videos/shuffle_draft.webm`, caption: 'Shuffle Draft', type: 'video' },
          ]}
          docsPath="/features/draft/"
          action={{ label: 'View Tournaments', href: '/tournaments' }}
        />
        <FeatureCard
          icon={Trophy}
          title="Tournament Brackets"
          description="Single elimination, double elimination, and round-robin formats with automatic bracket generation and match tracking."
          delay={0.3}
          gifSrc={`${ASSETS_BASE}/site_snapshots/bracket.png`}
          modalMedia={[
            { src: `${ASSETS_BASE}/site_snapshots/bracket.png`, caption: 'Bracket View', type: 'image' },
          ]}
          docsPath="/features/bracket/"
          action={{ label: 'Browse Tournaments', href: '/tournaments' }}
        />
        <FeatureCard
          icon={Users}
          title="Team Management"
          description="Create and manage rosters, track player stats, and coordinate with Discord integration."
          delay={0.4}
          docsPath="/features/team-management/"
          action={{ label: 'View Users', href: '/users' }}
        />
        <FeatureCard
          icon={Award}
          title="League System"
          description="Season-based competitive leagues with ELO ratings, standings, and match history."
          delay={0.5}
          docsPath="/features/planned/league-rating/"
          action={{ label: 'View Leagues', href: '/leagues' }}
          comingSoon
        />
        <FeatureCard
          icon={Shield}
          title="Discord Integration"
          description="Seamless Discord server integration for roster syncing and tournament announcements."
          delay={0.6}
          docsPath="/features/planned/discord-integration/"
          comingSoon
        />
      </div>
    </div>
  );
}
