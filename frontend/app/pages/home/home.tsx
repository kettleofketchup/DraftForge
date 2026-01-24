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
import {
  getGames,
  getLeagues,
  getOrganizations,
  getTournaments,
} from '~/components/api/api';
import { Badge } from '~/components/ui/badge';
import { Button } from '~/components/ui/button';

const FeatureCard = ({
  icon: Icon,
  title,
  description,
  delay,
  comingSoon,
}: {
  icon: React.ElementType;
  title: string;
  description: string;
  delay: number;
  comingSoon?: boolean;
}) => (
  <motion.div
    initial={{ opacity: 0, y: 20 }}
    animate={{ opacity: 1, y: 0 }}
    transition={{ duration: 0.5, delay }}
    className={`card bg-base-200/50 backdrop-blur border border-primary/10 hover:border-primary/30 transition-all duration-300 hover:shadow-lg hover:shadow-primary/5 ${comingSoon ? 'opacity-75' : ''}`}
  >
    <div className="card-body">
      <div className="flex items-start justify-between">
        <div className="w-12 h-12 rounded-lg bg-primary/10 flex items-center justify-center mb-4">
          <Icon className="w-6 h-6 text-primary" />
        </div>
        {comingSoon && (
          <Badge variant="outline" className="text-xs border-warning text-warning">
            Coming Soon
          </Badge>
        )}
      </div>
      <h3 className="card-title text-lg">{title}</h3>
      <p className="text-base-content/70 text-sm">{description}</p>
    </div>
  </motion.div>
);

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

  const { data: tournaments, isLoading: tournamentsLoading } = useQuery({
    queryKey: ['tournaments'],
    queryFn: () => getTournaments(),
    enabled: isClient,
  });

  const { data: games, isLoading: gamesLoading } = useQuery({
    queryKey: ['games'],
    queryFn: () => getGames(),
    enabled: isClient,
  });

  const { data: organizations, isLoading: orgsLoading } = useQuery({
    queryKey: ['organizations'],
    queryFn: () => getOrganizations(),
    enabled: isClient,
  });

  const { data: leagues, isLoading: leaguesLoading } = useQuery({
    queryKey: ['leagues'],
    queryFn: () => getLeagues(),
    enabled: isClient,
  });

  const isLoading = tournamentsLoading || gamesLoading || orgsLoading || leaguesLoading;

  if (isLoading || !tournaments || !games || !organizations || !leagues) {
    return <StatsSkeleton />;
  }

  return (
    <>
      <StatCard value={tournaments.length} label="Tournaments" delay={0.6} />
      <StatCard value={games.length} label="Games Played" delay={0.7} />
      <StatCard value={organizations.length} label="Organizations" delay={0.8} />
      <StatCard value={leagues.length} label="Leagues" delay={0.9} />
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
            The ultimate platform for Dota 2 tournament organization, team drafting, and competitive league management.
          </motion.p>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.3 }}
            className="flex flex-col sm:flex-row gap-4 justify-center"
          >
            <Button size="lg" className="!text-black" asChild>
              <a href="/tournaments">
                Browse Tournaments
                <ChevronRight className="w-4 h-4" />
              </a>
            </Button>
            <Button size="lg" variant="outline" className="shadow-md border-2 border-emerald-500 text-emerald-400 hover:bg-emerald-500/20" asChild>
              <a href="https://discord.gg/dtx" target="_blank" rel="noopener noreferrer">
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
              From casual in-house leagues to serious competitive tournaments, DraftForge has the tools to make it happen.
            </p>
          </motion.div>

          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
            <FeatureCard
              icon={Trophy}
              title="Tournament Brackets"
              description="Single elimination, double elimination, and round-robin formats with automatic bracket generation."
              delay={0.1}
            />
            <FeatureCard
              icon={Swords}
              title="Hero Draft System"
              description="Real-time captain's mode drafting with spectator view, timers, and pick/ban tracking."
              delay={0.2}
            />
            <FeatureCard
              icon={Users}
              title="Team Management"
              description="Create and manage rosters, track player stats, and coordinate with Discord integration."
              delay={0.3}
            />
            <FeatureCard
              icon={GitBranch}
              title="Team Draft Composition"
              description="Draft 40+ team members in minutes with Snake, Normal, and Shuffle draft modes balanced by MMR."
              delay={0.4}
            />
            <FeatureCard
              icon={Award}
              title="League System"
              description="Season-based competitive leagues with ELO ratings, standings, and match history."
              delay={0.5}
              comingSoon
            />
            <FeatureCard
              icon={Shield}
              title="Guild Discord Integration"
              description="Seamless Discord server integration for roster syncing and tournament announcements."
              delay={0.6}
              comingSoon
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
              <h2 className="text-3xl font-bold mb-4">Ready to Forge Your Tournament?</h2>
              <p className="text-base-content/70 mb-8 max-w-xl mx-auto">
                Join the growing community of Dota 2 organizers using DraftForge to create unforgettable competitive experiences.
              </p>
              <div className="flex flex-col sm:flex-row gap-4 justify-center">
                <Button size="lg" className="!text-black" asChild>
                  <a href="/tournaments">Get Started</a>
                </Button>
                <Button size="lg" variant="outline" className="shadow-md border-2 border-violet-500 text-violet-400 hover:bg-violet-500/20" asChild>
                  <a href="/about">Learn More</a>
                </Button>
              </div>
            </div>
          </div>
        </motion.div>
      </section>
    </div>
  );
}
