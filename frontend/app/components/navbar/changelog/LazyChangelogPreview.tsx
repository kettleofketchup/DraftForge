import { ArrowRight } from 'lucide-react';
import { lazy, Suspense } from 'react';
import { ErrorBoundary } from 'react-error-boundary';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';
import { Skeleton } from '~/components/ui/skeleton';

const loadPreview = () => import('./ChangelogPreview');
let ChangelogPreview = lazy(loadPreview);

function retryNextMount(): void {
  ChangelogPreview = lazy(loadPreview);
}

type LazyChangelogPreviewProps = {
  'data-testid': string;
  onNavigate?: () => void;
};

export function LazyChangelogPreview({
  'data-testid': testId,
  onNavigate,
}: LazyChangelogPreviewProps): React.JSX.Element {
  const { t } = useTranslation('navbar');

  return (
    <div data-testid={testId}>
      <ErrorBoundary
        onError={retryNextMount}
        fallback={
          <div className="flex flex-col gap-2 text-sm">
            <p className="text-muted-foreground">
              {t('nav.changelog_load_error')}
            </p>
            <Link
              to="/changelog"
              onClick={onNavigate}
              className="flex items-center gap-1 text-primary underline"
            >
              {t('nav.full_changelog')}
              <ArrowRight aria-hidden="true" className="size-3.5" />
            </Link>
          </div>
        }
      >
        <Suspense fallback={<Skeleton className="h-40 w-full" />}>
          <ChangelogPreview />
        </Suspense>
      </ErrorBoundary>
    </div>
  );
}
