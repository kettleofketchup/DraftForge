import { motion } from 'framer-motion';
import { getLogger } from '~/lib/logger';

const log = getLogger('TechnologyStack');

interface TechItem {
  readonly name: string;
  readonly description: string;
  readonly colorClass: string;
}
export function TechnologyStack() {
  log.debug('Rendering TechnologyStack component');

  const technologies: readonly TechItem[] = [
    {
      name: 'React',
      description: 'Frontend Framework',
      colorClass: 'text-blue-500',
    },
    {
      name: 'Django',
      description: 'Backend API',
      colorClass: 'text-white-500',
    },
    {
      name: 'Discord OAuth',
      description: 'Authentication & User Management',
      colorClass: 'text-success',
    },
    {
      name: 'ShadeCN',
      description: 'UI Components',
      colorClass: 'text-warning',
    },
  ];

  return (
    <div className="mt-12">
      <h2 className="text-3xl font-bold text-center text-primary mb-8">
        Built With Modern Technology
      </h2>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {technologies.map((tech) => (
          <motion.div whileHover={{ scale: 1.05 }} key={tech.name}>
            <div
              key={tech.name}
              className="card bg-base-200/50 backdrop-blur border border-primary/10 h-full"
            >
              <div className="card-body items-center text-center p-4">
                <h4 className={`font-semibold ${tech.colorClass}`}>
                  {tech.name}
                </h4>
                <p className="text-sm text-base-content/70">
                  {tech.description}
                </p>
              </div>
            </div>
          </motion.div>
        ))}
      </div>
    </div>
  );
}
