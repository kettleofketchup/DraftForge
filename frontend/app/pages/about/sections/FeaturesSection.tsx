import { motion } from 'framer-motion';
import React from 'react';
import { getLogger } from '~/lib/logger';
import { FeatureCard } from './FeatureCard';
const log = getLogger('FeaturesSection');

interface Feature {
  readonly title: string;
  readonly description: string;
  readonly colorClass: string;
  readonly icon: React.ReactNode;
}

export function FeaturesSection() {
  log.debug('Rendering FeaturesSection component');
  const [adder, setAdder] = React.useState(0);
  const features: readonly Feature[] = [
    {
      title: 'Member Management',
      description:
        'Organize your guild members, track their progress, and manage roles with our intuitive member management system.',
      colorClass: 'text-white',
      icon: (
        <svg
          className="w-6 h-6"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z"
          />
        </svg>
      ),
    },
    {
      title: 'Performance Analytics',
      description:
        'Detailed statistics and analytics to help track individual and team performance across matches and tournaments.',
      colorClass: 'text-white',
      icon: (
        <svg
          className="w-6 h-6"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v4a2 2 0 01-2 2H9a2 2 0 00-2 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2h2a2 2 0 012 2z"
          />
        </svg>
      ),
    },
    {
      title: 'Discord Integration',
      description:
        'Seamless integration with Discord for authentication and enhanced community interaction through our platform.',
      colorClass: 'text-success',
      icon: (
        <svg
          className="w-6 h-6"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"
          />
        </svg>
      ),
    },
    {
      title: 'Draft Assist & User Tracking',
      description:
        'Coordinate guild events, scrimmages, and tournaments with our built-in draft system.',
      colorClass: 'text-warning',
      icon: (
        <svg
          className="w-6 h-6"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
          />
        </svg>
      ),
    },
  ];

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-8 mb-12">
      {features.map((feature, index) => (
        <motion.div
          key={feature.title}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.5, delay: index * 0.1 }}
          whileHover={{
            scale: 1.05,
            transition: {
              delay: 0,
              duration: 0.2,
            },
          }}
        >
          <FeatureCard
            key={feature.title}
            title={feature.title}
            description={feature.description}
            icon={feature.icon}
            colorClass={feature.colorClass}
          />
        </motion.div>
      ))}
    </div>
  );
}
