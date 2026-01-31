import { useQuery } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import {
  Award,
  ChevronRight,
  Code2,
  GitBranch,
  Shield,
  Swords,
  Trophy,
  Users,
  Zap,
} from 'lucide-react';
import { Link } from 'react-router';
import { getHomeStats } from '~/components/api/api';
import { FeatureCard } from '~/components/feature/FeatureCard';
import { Badge } from '~/components/ui/badge';
import { Button } from '~/components/ui/button';

// Video/GIF assets (mounted at public/assets/docs in dev, copied during build)
const ASSETS_BASE = '/assets/docs';

const StatCard = ({
  value,
  label,
  delay,
}: {
  value: string | number;
  label: string;
  delay: number;
}) => (
  <motion.div
    initial={{ opacity: 0, scale: 0.9 }}
    animate={{ opacity: 1, scale: 1 }}
    transition={{ duration: 0.4, delay }}
    className="text-center"
  >
    <div className="text-4xl font-bold text-primary mb-1">{value}</div>
    <div className="text-sm text-base-content/60">{label}</div>
  </motion.div>
);

const StatsSection = () => {
  // Only fetch on client side to avoid SSR issues with auth
  const isClient = typeof window !== 'undefined';

  // Use the optimized home-stats endpoint that returns only counts
  const { data: stats, isLoading } = useQuery({
    queryKey: ['home-stats'],
    queryFn: () => getHomeStats(),
    enabled: isClient,
    staleTime: 5 * 60 * 1000, // Consider data fresh for 5 minutes
  });

  if (isLoading || !stats) {
    return <StatsSkeleton />;
  }

  return (
    <>
      <StatCard
        value={stats.tournament_count}
        label="Tournaments"
        delay={0.6}
      />
      <StatCard value={stats.game_count} label="Games Played" delay={0.7} />
      <StatCard
        value={stats.organization_count}
        label="Organizations"
        delay={0.8}
      />
      <StatCard value={stats.league_count} label="Leagues" delay={0.9} />
    </>
  );
};

const StatsSkeleton = () => (
  <>
    {[0.6, 0.7, 0.8, 0.9].map((delay, i) => (
      <motion.div
        key={i}
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.4, delay }}
        className="text-center"
      >
        <div className="h-10 w-16 bg-base-content/10 rounded animate-pulse mx-auto mb-1" />
        <div className="h-4 w-20 bg-base-content/10 rounded animate-pulse mx-auto" />
      </motion.div>
    ))}
  </>
);

export default function HomePage() {
  return (
    <div className="min-h-screen">
      {/* Hero Section */}
      <section className="relative overflow-hidden py-20 px-4">
        {/* Background Effects */}
        <div className="absolute inset-0 bg-gradient-to-br from-primary/5 via-transparent to-accent/5" />
        <div className="absolute top-20 left-10 w-72 h-72 bg-primary/10 rounded-full blur-3xl" />
        <div className="absolute bottom-20 right-10 w-96 h-96 bg-accent/10 rounded-full blur-3xl" />

        <div className="relative max-w-6xl mx-auto text-center">
          <motion.div
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6 }}
            className="flex flex-wrap gap-2 justify-center mb-6"
          >
            <Badge className="bg-primary/10 text-primary border-primary/20 px-4 py-1">
              <Zap className="w-3 h-3 mr-1" />
              Tournament Management Evolved
            </Badge>
            <Badge className="bg-success/10 text-success border-success/20 px-4 py-1">
              <Code2 className="w-3 h-3 mr-1" />
              100% Open Source
            </Badge>
          </motion.div>

          <motion.h1
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.1 }}
            className="text-5xl md:text-7xl font-bold mb-6"
          >
            <span className="bg-gradient-to-r from-primary via-accent to-primary bg-clip-text text-transparent">
              DraftForge
            </span>
          </motion.h1>

          <motion.p
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.2 }}
            className="text-xl md:text-2xl text-base-content/70 mb-8 max-w-2xl mx-auto"
          >
            The ultimate platform for Dota 2 tournament organization, team
            drafting, and competitive league management.
          </motion.p>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.3 }}
            className="flex flex-col sm:flex-row gap-4 justify-center"
          >
            <Button size="lg" className="" asChild>
              <Link to="/tournaments">
                Browse Tournaments
                <ChevronRight className="w-4 h-4" />
              </Link>
            </Button>
            <Button size="lg" className="secondary" asChild>
              <a
                href="https://discord.gg/6xYb7RUn8a"
                target="_blank"
                rel="noopener noreferrer"
              >
                Join Discord
              </a>
            </Button>
          </motion.div>

          {/* Stats */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.8, delay: 0.5 }}
            className="grid grid-cols-2 md:grid-cols-4 gap-8 mt-16 pt-8 border-t border-base-content/10"
          >
            <StatsSection />
          </motion.div>
        </div>
      </section>

      {/* Features Section */}
      <section className="py-20 px-4 bg-base-200/30">
        <div className="max-w-6xl mx-auto">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.5 }}
            className="text-center mb-12"
          >
            <h2 className="text-3xl md:text-4xl font-bold mb-4">
              Everything You Need to Run
              <span className="text-primary"> Competitive Events</span>
            </h2>
            <p className="text-base-content/60 max-w-2xl mx-auto">
              From casual in-house leagues to serious competitive tournaments,
              DraftForge has the tools to make it happen.
            </p>
          </motion.div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
            <FeatureCard
              icon={Trophy}
              title="Tournament Brackets"
              description="Single elimination, double elimination, and round-robin formats with automatic bracket generation."
              delay={0.1}
              gifSrc={`${ASSETS_BASE}/site_snapshots/bracket.png`}
              docsPath="/features/bracket/"
            />
            <FeatureCard
              icon={Swords}
              title="Hero Draft System"
              description="Real-time captain's mode drafting with spectator view, timers, and pick/ban tracking."
              delay={0.2}
              gifSrc={`${ASSETS_BASE}/gifs/captain1_herodraft.gif`}
              quickMedia={[
                { src: `${ASSETS_BASE}/gifs/captain1_herodraft.gif`, caption: 'Captain 1 Perspective', type: 'gif' },
                { src: `${ASSETS_BASE}/gifs/captain2_herodraft.gif`, caption: 'Captain 2 Perspective', type: 'gif' },
              ]}
              modalMedia={[
                { src: `${ASSETS_BASE}/videos/captain1_herodraft.webm`, caption: 'Captain 1 Perspective', type: 'video' },
                { src: `${ASSETS_BASE}/videos/captain2_herodraft.webm`, caption: 'Captain 2 Perspective', type: 'video' },
              ]}
              docsPath="/features/herodraft/"
            />
            <FeatureCard
              icon={GitBranch}
              title="Team Draft Composition"
              description="Draft 40+ team members in minutes with Snake, Normal, and Shuffle draft modes balanced by MMR."
              delay={0.3}
              gifSrc={`${ASSETS_BASE}/gifs/snake_draft.gif`}
              quickMedia={[
                { src: `${ASSETS_BASE}/gifs/snake_draft.gif`, caption: 'Snake Draft', type: 'gif' },
                { src: `${ASSETS_BASE}/gifs/shuffle_draft.gif`, caption: 'Shuffle Draft', type: 'gif' },
              ]}
              modalMedia={[
                { src: `${ASSETS_BASE}/videos/snake_draft.webm`, caption: 'Snake Draft', type: 'video' },
                { src: `${ASSETS_BASE}/videos/shuffle_draft.webm`, caption: 'Shuffle Draft', type: 'video' },
              ]}
              docsPath="/features/draft/"
            />
            <FeatureCard
              icon={Users}
              title="Team Management"
              description="Create and manage rosters, track player stats, and coordinate with Discord integration."
              delay={0.4}
              docsPath="/features/team-management/"
            />
            <FeatureCard
              icon={Award}
              title="League System"
              description="Season-based competitive leagues with ELO ratings, standings, and match history."
              delay={0.5}
              comingSoon
              docsPath="/features/planned/league-rating/"
            />
            <FeatureCard
              icon={Shield}
              title="Guild Discord Integration"
              description="Seamless Discord server integration for roster syncing and tournament announcements."
              delay={0.6}
              comingSoon
              docsPath="/features/planned/discord-integration/"
            />
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="py-20 px-4">
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          whileInView={{ opacity: 1, scale: 1 }}
          viewport={{ once: true }}
          transition={{ duration: 0.5 }}
          className="max-w-4xl mx-auto"
        >
          <div className="card bg-gradient-to-r from-primary/10 via-accent/5 to-primary/10 border border-primary/20">
            <div className="card-body text-center py-12">
              <h2 className="text-3xl font-bold mb-4">
                Ready to Forge Your Tournament?
              </h2>
              <p className="text-base-content/70 mb-8 max-w-xl mx-auto">
                Join the growing community of Dota 2 organizers using DraftForge
                to create unforgettable competitive experiences.
              </p>
              <div className="flex flex-col sm:flex-row gap-4 justify-center">
                <Button size="lg" className="!text-black" asChild>
                  <Link to="/tournaments">Get Started</Link>
                </Button>
                <Button
                  size="lg"
                  variant="secondary"
                  asChild
                >
                  <a
                    href="https://kettleofketchup.github.io/DraftForge/"
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    Learn More
                  </a>
                </Button>
              </div>
            </div>
          </div>
        </motion.div>
      </section>
    </div>
  );
}
