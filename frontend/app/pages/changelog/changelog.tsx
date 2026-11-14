import { useTranslation } from 'react-i18next';
import { ChangelogMarkdown } from '~/components/navbar/changelog/ChangelogMarkdown';
import { allReleases } from '~/lib/changelog';

export function ChangelogPage(): React.JSX.Element {
  const { t } = useTranslation('navbar');
  const releases = allReleases();

  return (
    <main
      data-testid="changelog-page"
      className="container mx-auto max-w-3xl px-4 py-8 flex flex-col gap-8"
    >
      <h1 className="text-3xl font-bold text-foreground">
        {t('nav.changelog')}
      </h1>
      {releases.map((release) => (
        <section
          key={release.version}
          data-testid="changelog-release"
          className="flex flex-col gap-3 border-b border-border pb-6"
        >
          <h2 className="text-xl font-semibold text-foreground">
            {release.version} – {release.date}
          </h2>
          <ChangelogMarkdown markdown={release.body} headingOffset={0} />
        </section>
      ))}
    </main>
  );
}
