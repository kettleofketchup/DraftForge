import React from 'react';
import { getLogger } from '~/lib/logger';

const log = getLogger('FeatureCard');

interface FeatureCardProps {
  readonly title: string;
  readonly description: string;
  readonly icon: React.ReactNode;
  readonly colorClass: string;
}

export function FeatureCard({ title, description, icon, colorClass }: FeatureCardProps) {
  log.debug(`Rendering FeatureCard for ${title}`);

  return (
    <div className="card bg-base-200 shadow-lg">
      <div className="card-body">
        <h3 className={`card-title ${colorClass}`}>
          {icon}
          {title}
        </h3>
        <p className="text-base-content">{description}</p>
      </div>
    </div>
  );
}
