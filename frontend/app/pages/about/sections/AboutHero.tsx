import { Code2 } from 'lucide-react';
import { Badge } from '~/components/ui/badge';
import { getLogger } from '~/lib/logger';

const log = getLogger('AboutHero');
export function AboutHero() {
  log.debug('Rendering AboutHero component');

  return (
    <section className="relative overflow-hidden py-20 px-4">
      {/* Background Effects - matching home page */}
      <div className="absolute inset-0 bg-gradient-to-br from-primary/5 via-transparent to-accent/5" />
      <div className="absolute top-10 left-10 w-72 h-72 bg-primary/10 rounded-full blur-3xl" />
      <div className="absolute bottom-10 right-10 w-96 h-96 bg-accent/10 rounded-full blur-3xl" />

      <div className="relative max-w-4xl mx-auto text-center">
        <Badge className="mb-6 bg-success/10 text-success border-success/20 px-4 py-1">
          <Code2 className="w-3 h-3 mr-1" />
          100% Open Source
        </Badge>
        <h1 className="text-5xl md:text-6xl font-bold mb-6">
          <span className="bg-gradient-to-r from-primary via-accent to-primary bg-clip-text text-transparent">
            About DraftForge
          </span>
        </h1>
        <p className="text-xl text-base-content/70">
          Tournament & Guild Management for Dota 2 Communities
        </p>
      </div>
    </section>
  );
}
