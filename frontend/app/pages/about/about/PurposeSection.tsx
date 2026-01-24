import { getLogger } from '~/lib/logger';

const log = getLogger('PurposeSection');

export function PurposeSection() {
  log.debug('Rendering PurposeSection component');

  return (
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
            DraftForge is dedicated to providing a comprehensive management solution for Dota 2 gaming organizations.
            This platform serves as the central hub for all guild-related activities, offering tools and features
            that enhance our community experience.
          </p>
          <p className="text-base-content">
            Our mission is to streamline guild operations, facilitate better communication among members,
            and provide valuable insights into team performance and statistics. Whether you're a casual player
            or a competitive esports enthusiast, DraftForge offers the tools you need to succeed.
          </p>
        </div>
      </div>
    </div>
  );
}
