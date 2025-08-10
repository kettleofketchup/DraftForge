import { motion } from 'framer-motion';
import { getLogger } from '~/lib/logger';

const log = getLogger('PurposeSection');
export function PurposeSection() {
  log.debug('Rendering PurposeSection component');

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
      <div className="card bg-base-200 shadow-lg mb-12">
        <div className="card-body">
          <h2 className="card-title text-3xl text-primary mb-6">
            <svg
              className="w-8 h-8"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M13 10V3L4 14h7v7l9-11h-7z"
              />
            </svg>
            Our Purpose
          </h2>
          <div className="prose max-w-none">
            <p className="text-lg text-base-content mb-4">
              This site is dedicated to providing a comprehensive management
              solution for our Dota 2 gaming organization. This platform serves
              as the central hub for all guild-related activities, offering
              tools and features that enhance our community experience.
            </p>
            <p className="text-base-content">
              DTX is a competitive, community‑driven Dota 2 guild focused on
              growth, teamwork, and consistent improvement. This site supports
              DTX operations— coordinating rosters and scrims, publishing
              schedules, tracking match stats, and keeping everyone aligned
              through Discord integration. Whether you’re grinding ranked,
              scrimming, or preparing for leagues, DTX members can find tools,
              resources, and updates here to play smarter together.
            </p>
          </div>
        </div>
      </div>
    </motion.div>
  );
}
