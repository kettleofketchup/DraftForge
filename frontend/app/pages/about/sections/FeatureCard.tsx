import React from 'react';
import { getLogger } from '~/lib/logger';

const log = getLogger('FeatureCard');

interface FeatureCardProps {
  readonly title: string;
  readonly description: string;
  readonly icon: React.ReactNode;
  readonly colorClass: string;
}

export function FeatureCard({
  title,
  description,
  icon,
  colorClass,
}: FeatureCardProps) {
  log.debug(`Rendering FeatureCard for ${title}`);

  return (
    <div className="card bg-base-200/50 backdrop-blur border border-primary/10 hover:border-primary/30 transition-all duration-300 h-full">
      <div className="card-body">
        <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center mb-2">
          <span className={colorClass}>{icon}</span>
        </div>
        <h3 className="card-title text-lg">{title}</h3>
        <p className="text-base-content/70 text-sm">{description}</p>
      </div>
    </div>
  );
}
