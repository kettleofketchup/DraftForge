import { useTranslation } from 'react-i18next';
import { latestReleases } from '~/lib/changelog';
import { ChangelogMarkdown } from './ChangelogMarkdown';

export default function ChangelogPreview(): React.JSX.Element {
  const { t } = useTranslation('navbar');
  const releases = latestReleases(2);

  return (
    <div className="flex flex-col gap-4">
      {releases.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          {t('nav.changelog_empty')}
        </p>
      ) : (
        releases.map((release) => (
          <section key={release.version} className="flex flex-col gap-2">
            <h3 className="text-sm font-semibold text-foreground">
              {release.version} – {release.date}
            </h3>
            <ChangelogMarkdown markdown={release.body} headingOffset={1} />
          </section>
        ))
      )}
    </div>
  );
}
