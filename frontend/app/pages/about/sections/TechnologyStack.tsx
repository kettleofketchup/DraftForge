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
      colorClass: 'text-accent',
    },
    {
      name: 'Django',
      description: 'Backend API',
      colorClass: 'text-secondary',
    },
    {
      name: 'TypeScript',
      description: 'Type Safety',
      colorClass: 'text-success',
    },
    {
      name: 'Tailwind CSS',
      description: 'Styling',
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
            <div key={tech.name} className="card bg-base-200 shadow-sm">
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
