import { motion } from 'framer-motion';
import { GitBranch, Heart, Users } from 'lucide-react';
import { getLogger } from '~/lib/logger';

const log = getLogger('HistorySection');

export function HistorySection() {
  log.debug('Rendering HistorySection component');

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.5, delay: 0.2 }}
    >
      <div className="card bg-base-200/50 backdrop-blur border border-primary/10 mb-12">
        <div className="card-body">
          <h2 className="card-title text-2xl text-primary mb-6 flex items-center gap-2">
            <GitBranch className="w-6 h-6 flex-shrink-0" />
            <span>Our History</span>
          </h2>

          <div className="space-y-6">
            {/* Origin Story */}
            <div className="flex gap-4">
              <div className="flex-shrink-0">
                <div className="w-10 h-10 rounded-full bg-primary/20 flex items-center justify-center">
                  <Heart className="w-5 h-5 text-primary" />
                </div>
              </div>
              <div>
                <h3 className="font-semibold text-lg mb-1">Born from DTX</h3>
                <p className="text-base-content/80">
                  DraftForge started as an internal tool for DTX, a competitive
                  Dota 2 guild ranked #1 on US East. Built to coordinate rosters, manage
                  scrims, track stats, and keep the community aligned through Discord integration.
                </p>
              </div>
            </div>

            {/* Open Source */}
            <div className="flex gap-4">
              <div className="flex-shrink-0">
                <div className="w-10 h-10 rounded-full bg-accent/20 flex items-center justify-center">
                  <Users className="w-5 h-5 text-accent" />
                </div>
              </div>
              <div>
                <h3 className="font-semibold text-lg mb-1">Open Sourced for Everyone</h3>
                <p className="text-base-content/80">
                  We realized other Dota 2 communities could benefit from the same tools,
                  so we open sourced the project. Now any guild, team, or tournament organizer
                  can use DraftForge to manage their community.
                </p>
              </div>
            </div>
          </div>

          {/* Thank you note */}
          <div className="mt-6 p-4 bg-base-content/5 rounded-lg border border-base-content/10">
            <p className="text-sm text-base-content/70 italic">
              Special thanks to DTX and its members for supporting the development of this
              platform from the beginning. Your feedback and enthusiasm made this possible.
            </p>
          </div>
        </div>
      </div>
    </motion.div>
  );
}
