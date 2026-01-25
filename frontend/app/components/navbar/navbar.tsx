import { Slot } from '@radix-ui/react-slot';
import * as React from 'react';
import { memo } from 'react';
import { Link } from 'react-router';
import { cn } from '~/lib/utils';
import { useUserStore } from '../../store/userStore';
import { Tooltip, TooltipContent, TooltipTrigger } from '../ui/tooltip';
import { LoginWithDiscordButton } from './login';
import { MobileNav } from './MobileNav';

const GITHUB_REPO_URL = 'https://github.com/kettleofketchup/draftforge';
const DOCS_URL = 'https://kettleofketchup.github.io/DraftForge/';
const BUG_REPORT_URL = `${GITHUB_REPO_URL}/issues/new?template=bug_report.md`;

/**
 * NavItem - Navigation item with responsive display states
 *
 * BREAKPOINT LAYOUT (for non-mobile nav, visible at md/768px+):
 * ┌─────────────────────────────────────────────────────────────────────────┐
 * │ SMALL (md to 1099px: 768px - 1099px)                                    │
 * │ - Icons only                                                            │
 * │ - Tooltip on hover shows title + subtitle (if showSubtitleTooltip)      │
 * │ - Controlled by: hideTextOnSmall && 'hidden min-[1100px]:flex'          │
 * ├─────────────────────────────────────────────────────────────────────────┤
 * │ MEDIUM (1100px to xl: 1100px - 1279px)                                  │
 * │ - Icons + title text (horizontal layout)                                │
 * │ - Subtitle still hidden                                                 │
 * │ - Controlled by: min-[1100px]:flex shows text                           │
 * ├─────────────────────────────────────────────────────────────────────────┤
 * │ LARGE (xl+: 1280px+)                                                    │
 * │ - Icons + title + subtitle (vertical/stacked layout)                    │
 * │ - Full content display                                                  │
 * │ - Controlled by: xl:flex-col xl:items-center, subtitle xl:block         │
 * └─────────────────────────────────────────────────────────────────────────┘
 *
 * BREAKPOINTS USED:
 * - md: 768px  (NavLinks becomes visible, MobileNav hamburger hidden)
 * - 1100px: Custom breakpoint (Text appears if hideTextOnSmall=true)
 * - xl: 1280px (Subtitle appears, layout becomes vertical)
 */
interface NavItemProps
  extends Omit<React.AnchorHTMLAttributes<HTMLAnchorElement>, 'href'> {
  icon?: React.ReactNode;
  title: string;
  subtitle?: string;
  badge?: React.ReactNode;
  asChild?: boolean;
  /** When true: hides text below 1100px, shows icons only with tooltip */
  hideTextOnSmall?: boolean;
  /** Show subtitle as tooltip on small screens (below xl) */
  showSubtitleTooltip?: boolean;
  /** Use for internal routes (uses React Router Link) */
  to?: string;
  /** Use for external links (uses <a> tag) */
  href?: string;
}

const NavItem = React.forwardRef<HTMLAnchorElement, NavItemProps>(
  (
    {
      className,
      icon,
      title,
      subtitle,
      badge,
      asChild = false,
      hideTextOnSmall = false,
      showSubtitleTooltip = false,
      to,
      href,
      ...props
    },
    ref,
  ) => {
    const baseClassName = cn(
      // Base layout with responsive gap: tight at medium (1100px+), expanded at xl
      'flex items-center gap-1 xl:gap-2 rounded-md px-1.5 xl:px-2 py-1.5 h-9',
      'text-sm font-medium',
      'text-text-primary',
      'hover:bg-base-400/50',
      'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
      'transition-colors',
      className,
    );

    const content = (
      <>
        {/* Icon - always visible */}
        {icon && <span className="shrink-0">{icon}</span>}

        {/* Text container - visibility controlled by hideTextOnSmall */}
        <div
          className={cn(
            // Base: horizontal layout
            'flex min-w-0 items-center',
            // LARGE (xl+): switch to vertical/stacked layout
            'xl:flex-col xl:items-center',
            // hideTextOnSmall: hidden below 1100px, visible at 1100px+
            // This creates: icons-only (md-1099px) → icons+text (1100px+)
            hideTextOnSmall && 'hidden min-[1100px]:flex',
          )}
        >
          {/* Title + badge row */}
          <div className="flex items-center justify-center gap-1">
            <span className="text-xs font-bold leading-normal truncate text-center text-outline-sm">
              {title}
            </span>
            {badge}
          </div>

          {/* Subtitle - only visible at xl+ */}
          {subtitle && (
            <span className="text-[10px] text-text-muted leading-normal truncate hidden xl:block text-center">
              {subtitle}
            </span>
          )}
        </div>
      </>
    );

    // Render the appropriate component based on props
    let navContent: React.ReactElement;
    if (asChild) {
      navContent = (
        <Slot ref={ref} className={baseClassName} {...props}>
          {content}
        </Slot>
      );
    } else if (to) {
      navContent = (
        <Link ref={ref} to={to} className={baseClassName} {...props}>
          {content}
        </Link>
      );
    } else {
      navContent = (
        <a ref={ref} href={href} className={baseClassName} {...props}>
          {content}
        </a>
      );
    }

    // Wrap with tooltip for small screens if enabled
    if (showSubtitleTooltip && subtitle) {
      return (
        <Tooltip>
          <TooltipTrigger asChild>{navContent}</TooltipTrigger>
          <TooltipContent className="xl:hidden">
            <p className="font-medium">{title}</p>
            <p className="text-xs opacity-80">{subtitle}</p>
          </TooltipContent>
        </Tooltip>
      );
    }

    return navContent;
  },
);
NavItem.displayName = 'NavItem';

const GitHubIcon = () => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 24 24"
    fill="currentColor"
    className="h-5 w-5"
    aria-hidden="true"
  >
    <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z" />
  </svg>
);

const StarIcon = () => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 24 24"
    fill="currentColor"
    className="h-4 w-4"
    aria-hidden="true"
  >
    <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z" />
  </svg>
);

// Hook to fetch GitHub star count
const useGitHubStars = () => {
  const [stars, setStars] = React.useState<number | null>(null);
  const [isLoading, setIsLoading] = React.useState(true);

  React.useEffect(() => {
    const fetchStars = async () => {
      setIsLoading(true);
      try {
        const response = await fetch(
          'https://api.github.com/repos/kettleofketchup/draftforge',
        );
        if (response.ok) {
          const data = await response.json();
          setStars(data.stargazers_count);
        }
      } catch (error) {
        // Silently fail - stars will just not be shown
      } finally {
        setIsLoading(false);
      }
    };
    fetchStars();
  }, []);

  return { stars, isLoading };
};

const DocsIcon = () => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    className="h-5 w-5"
    aria-hidden="true"
  >
    <path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1 0-5H20" />
  </svg>
);

const BugIcon = () => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    className="h-5 w-5"
    aria-hidden="true"
  >
    <path d="m8 2 1.88 1.88" />
    <path d="M14.12 3.88 16 2" />
    <path d="M9 7.13v-1a3.003 3.003 0 1 1 6 0v1" />
    <path d="M12 20c-3.3 0-6-2.7-6-6v-3a4 4 0 0 1 4-4h4a4 4 0 0 1 4 4v3c0 3.3-2.7 6-6 6" />
    <path d="M12 20v-9" />
    <path d="M6.53 9C4.6 8.8 3 7.1 3 5" />
    <path d="M6 13H2" />
    <path d="M3 21c0-2.1 1.7-3.9 3.8-4" />
    <path d="M20.97 5c0 2.1-1.6 3.8-3.5 4" />
    <path d="M22 13h-4" />
    <path d="M17.2 17c2.1.1 3.8 1.9 3.8 4" />
  </svg>
);

// Navigation Icons
const TrophyIcon = () => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    className="h-5 w-5"
    aria-hidden="true"
  >
    <path d="M6 9H4.5a2.5 2.5 0 0 1 0-5H6" />
    <path d="M18 9h1.5a2.5 2.5 0 0 0 0-5H18" />
    <path d="M4 22h16" />
    <path d="M10 14.66V17c0 .55-.47.98-.97 1.21C7.85 18.75 7 20.24 7 22" />
    <path d="M14 14.66V17c0 .55.47.98.97 1.21C16.15 18.75 17 20.24 17 22" />
    <path d="M18 2H6v7a6 6 0 0 0 12 0V2Z" />
  </svg>
);

const UsersIcon = () => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    className="h-5 w-5"
    aria-hidden="true"
  >
    <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
    <circle cx="9" cy="7" r="4" />
    <path d="M22 21v-2a4 4 0 0 0-3-3.87" />
    <path d="M16 3.13a4 4 0 0 1 0 7.75" />
  </svg>
);

const BuildingIcon = () => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    className="h-5 w-5"
    aria-hidden="true"
  >
    <rect width="16" height="20" x="4" y="2" rx="2" ry="2" />
    <path d="M9 22v-4h6v4" />
    <path d="M8 6h.01" />
    <path d="M16 6h.01" />
    <path d="M12 6h.01" />
    <path d="M12 10h.01" />
    <path d="M12 14h.01" />
    <path d="M16 10h.01" />
    <path d="M16 14h.01" />
    <path d="M8 10h.01" />
    <path d="M8 14h.01" />
  </svg>
);

const LeagueIcon = () => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    className="h-5 w-5"
    aria-hidden="true"
  >
    <path d="M12 2v4" />
    <path d="m6.8 15-3.5 2" />
    <path d="m20.7 17-3.5-2" />
    <path d="M6.8 9 3.3 7" />
    <path d="m20.7 7-3.5 2" />
    <circle cx="12" cy="12" r="6" />
    <path d="M12 10v4l2 1" />
  </svg>
);

const AdminIcon = () => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    className="h-5 w-5"
    aria-hidden="true"
  >
    <path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z" />
    <circle cx="12" cy="12" r="3" />
  </svg>
);

const AboutIcon = () => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    className="h-5 w-5"
    aria-hidden="true"
  >
    <circle cx="12" cy="12" r="10" />
    <path d="M12 16v-4" />
    <path d="M12 8h.01" />
  </svg>
);

// Star badge component for GitHub (compact, right-aligned)
const StarBadge = ({
  count,
  isLoading,
}: {
  count: number | null;
  isLoading?: boolean;
}) => {
  if (isLoading) {
    return (
      <span className="inline-flex items-center gap-0.5 text-[10px] bg-base-400 text-text-primary rounded px-1 py-0.5 leading-none">
        <svg
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 24 24"
          fill="currentColor"
          className="h-3 w-3 animate-pulse text-warning"
          aria-hidden="true"
        >
          <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z" />
        </svg>
        <span className="w-3 h-2.5 bg-base-300 rounded animate-pulse" />
      </span>
    );
  }
  if (count === null) return null;
  return (
    <span className="inline-flex items-center gap-0.5 text-[10px] bg-base-400 text-text-primary font-semibold rounded px-1 py-0.5 leading-none">
      <svg
        xmlns="http://www.w3.org/2000/svg"
        viewBox="0 0 24 24"
        fill="currentColor"
        className="h-3 w-3 text-warning"
        aria-hidden="true"
      >
        <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z" />
      </svg>
      {count}
    </span>
  );
};

// External links (GitHub, Docs, Bug Report) using NavItem
// Icons always visible, text hidden on small screens
const ExternalLinks = ({ className }: { className?: string }) => {
  const { stars, isLoading } = useGitHubStars();

  return (
    <div
      className={cn(
        'flex items-center gap-0.5 lg:gap-1 mr-1 lg:mr-2',
        className,
      )}
    >
      <NavItem
        href={GITHUB_REPO_URL}
        target="_blank"
        rel="noopener noreferrer"
        icon={<GitHubIcon />}
        title="GitHub"
        subtitle="Begging for Stars"
        badge={<StarBadge count={stars} isLoading={isLoading} />}
        aria-label="Star us on GitHub"
        hideTextOnSmall
        className="[&_svg]:text-text-primary"
      />
      <NavItem
        href={DOCS_URL}
        target="_blank"
        rel="noopener noreferrer"
        icon={<DocsIcon />}
        title="Docs"
        subtitle="Secret Sauce"
        aria-label="Documentation"
        hideTextOnSmall
        showSubtitleTooltip
        className="[&_svg]:text-info"
      />
      <NavItem
        href={BUG_REPORT_URL}
        target="_blank"
        rel="noopener noreferrer"
        icon={<BugIcon />}
        title="Report Issue"
        subtitle="Help us fix it"
        className="[&_svg]:text-destructive text-destructive hover:text-destructive hover:[&_svg]:text-red-400"
        aria-label="Report a Bug"
        hideTextOnSmall
      />
    </div>
  );
};

// Main navigation with icons + text using NavItem
// Icons always visible, text hidden on small screens
const NavLinks = ({ className }: { className?: string }) => {
  const currentUser = useUserStore((state) => state.currentUser);

  return (
    <div className={cn('flex items-center gap-0.5 lg:gap-1', className)}>
      <NavItem
        to="/about"
        icon={<AboutIcon />}
        title="About"
        subtitle="Who we are"
        hideTextOnSmall
        className="[&_svg]:text-info"
      />
      <NavItem
        to="/tournaments"
        icon={<TrophyIcon />}
        title="Tournaments"
        subtitle="Compete & win"
        hideTextOnSmall
        className="[&_svg]:text-warning"
      />
      <NavItem
        to="/users"
        icon={<UsersIcon />}
        title="Users"
        subtitle="Find players"
        hideTextOnSmall
        className="[&_svg]:text-interactive"
      />
      <NavItem
        to="/organizations"
        icon={<BuildingIcon />}
        title="Organizations"
        subtitle="Communities"
        hideTextOnSmall
        className="[&_svg]:text-secondary"
      />
      <NavItem
        to="/leagues"
        icon={<LeagueIcon />}
        title="Leagues"
        subtitle="Ranked play"
        hideTextOnSmall
        className="[&_svg]:text-primary"
      />
      {currentUser?.is_staff && (
        <NavItem
          to="/admin"
          icon={<AdminIcon />}
          title="Admin"
          subtitle="Manage site"
          hideTextOnSmall
          className="[&_svg]:text-success"
        />
      )}
    </div>
  );
};

const HomeIcon = () => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    className="h-6 w-6"
    aria-hidden="true"
  >
    {/* Roof */}
    <path d="M3 12l9-9 9 9" />
    {/* House body */}
    <path d="M5 10v10a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V10" />
    {/* Door */}
    <path d="M9 21v-6a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v6" />
  </svg>
);

const SiteLogo = () => {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Link
          className="p-2 flex-shrink-0 hidden md:flex items-center"
          to="/"
          aria-label="Home"
        >
          <HomeIcon />
        </Link>
      </TooltipTrigger>
      <TooltipContent>Home</TooltipContent>
    </Tooltip>
  );
};

// Mobile home link - shown only on small screens, integrated into MobileNav
const MobileHomeLink = () => {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Link
          className="p-2 flex-shrink-0 md:hidden flex items-center"
          to="/"
          aria-label="Home"
        >
          <HomeIcon />
        </Link>
      </TooltipTrigger>
      <TooltipContent>Home</TooltipContent>
    </Tooltip>
  );
};

export const ResponsiveAppBar: React.FC = memo(() => {
  return (
    <header>
      <nav
        className="sticky z-50 top-0 navbar bg-base-600 shadow-elevated border-b border-border p-0"
        role="navigation"
        aria-label="Main navigation"
      >
        <div className="navbar-start flex-1">
          <MobileNav />
          <MobileHomeLink />
          <SiteLogo />
          <NavLinks className="hidden md:flex" />
        </div>
        <div className="navbar-end">
          <ExternalLinks className="hidden md:flex" />
          <LoginWithDiscordButton />
        </div>
      </nav>
    </header>
  );
});
export default ResponsiveAppBar;
