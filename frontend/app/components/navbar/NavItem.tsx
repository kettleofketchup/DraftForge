import * as React from 'react';
import { Link } from 'react-router';
import { cn } from '~/lib/utils';
import { Tooltip, TooltipContent, TooltipTrigger } from '../ui/tooltip';

/**
 * NavItem label tiers above md (#252). `main` labels follow the left group's
 * @container width, i.e. whatever the right group leaves; `external` labels
 * follow the viewport and collapse first.
 */
export const LABEL_TIERS = {
  main: {
    text: 'hidden @min-[700px]:flex',
    stacked: '@min-[840px]:flex-col',
    subtitle: 'hidden @min-[840px]:block',
    tooltip: '@min-[840px]:hidden',
  },
  external: {
    text: 'hidden min-[1600px]:flex',
    stacked: 'min-[1920px]:flex-col',
    subtitle: 'hidden min-[1920px]:block',
    tooltip: 'min-[1920px]:hidden',
  },
} as const;

export type LabelTier = keyof typeof LABEL_TIERS;

type NavItemBaseProps = {
  icon?: React.ReactNode;
  title: string;
  subtitle?: string;
  badge?: React.ReactNode;
  /** Shown after the text at every width, e.g. a dropdown chevron */
  indicator?: React.ReactNode;
  /** Which LABEL_TIERS breakpoints collapse the label to the icon */
  tier: LabelTier;
  /** Show the subtitle as a tooltip while it is not shown inline */
  showSubtitleTooltip?: boolean;
  /** Custom class for title text (overrides default color) */
  titleClassName?: string;
  /** Test ID for Playwright/testing - auto-generated from route if not provided */
  'data-testid'?: string;
};

type NavItemAnchorProps = NavItemBaseProps &
  Omit<React.ComponentPropsWithoutRef<'a'>, 'href' | 'type' | 'title'> & {
    as?: undefined;
    /** Use for internal routes (uses React Router Link) */
    to?: string;
    /** Use for external links (uses <a> tag) */
    href?: string;
  };

type NavItemButtonProps = NavItemBaseProps &
  Omit<React.ComponentPropsWithoutRef<'button'>, 'title'> & { as: 'button' };

export type NavItemProps = NavItemAnchorProps | NavItemButtonProps;

export const NavItem = React.forwardRef<HTMLElement, NavItemProps>(
  (props, ref) => {
    const {
      icon,
      title,
      subtitle,
      badge,
      indicator,
      tier,
      showSubtitleTooltip = false,
      titleClassName,
      'data-testid': dataTestId,
    } = props;
    const tiers = LABEL_TIERS[tier];
    const to = props.as === 'button' ? undefined : props.to;
    const testId =
      dataTestId || (to ? `nav-link-${to.replace(/^\//, '')}` : undefined);
    const baseClassName = cn(
      'flex items-center gap-1 xl:gap-2 rounded-md px-1.5 xl:px-2 py-1.5 h-9',
      'text-sm font-medium',
      'text-text-primary',
      'hover:bg-base-400/50',
      'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
      'transition-colors',
      props.className,
    );

    const content = (
      <>
        {icon && <span className="shrink-0">{icon}</span>}
        <div
          className={cn(
            'items-center whitespace-nowrap',
            tiers.text,
            tiers.stacked,
          )}
        >
          <div className="flex items-center justify-center gap-1">
            <span
              className={cn(
                'text-xs font-bold leading-normal text-center text-outline-sm text-primary',
                titleClassName,
              )}
            >
              {title}
            </span>
            {badge}
          </div>
          {subtitle && (
            <span
              className={cn(
                'text-[10px] text-text-muted leading-normal text-center',
                tiers.subtitle,
              )}
            >
              {subtitle}
            </span>
          )}
        </div>
        {indicator}
      </>
    );

    let navContent: React.ReactElement;
    if (props.as === 'button') {
      const {
        as: _as,
        className: _className,
        icon: _icon,
        title: _title,
        subtitle: _subtitle,
        badge: _badge,
        indicator: _indicator,
        tier: _tier,
        showSubtitleTooltip: _showSubtitleTooltip,
        titleClassName: _titleClassName,
        'data-testid': _dataTestId,
        ...buttonRest
      } = props;
      // Plain button: shadcn Button's ghost and scale classes differ from the sibling links.
      navContent = (
        <button
          ref={ref as React.Ref<HTMLButtonElement>}
          type="button"
          className={baseClassName}
          data-testid={testId}
          aria-label={title}
          {...buttonRest}
        >
          {content}
        </button>
      );
    } else {
      const {
        as: _as,
        className: _className,
        icon: _icon,
        title: _title,
        subtitle: _subtitle,
        badge: _badge,
        indicator: _indicator,
        tier: _tier,
        showSubtitleTooltip: _showSubtitleTooltip,
        titleClassName: _titleClassName,
        'data-testid': _dataTestId,
        to: _to,
        href,
        ...anchorRest
      } = props;
      navContent = to ? (
        <Link
          ref={ref as React.Ref<HTMLAnchorElement>}
          to={to}
          className={baseClassName}
          data-testid={testId}
          aria-label={title}
          {...anchorRest}
        >
          {content}
        </Link>
      ) : (
        <a
          ref={ref as React.Ref<HTMLAnchorElement>}
          href={href}
          className={baseClassName}
          data-testid={testId}
          aria-label={title}
          {...anchorRest}
        >
          {content}
        </a>
      );
    }

    if (showSubtitleTooltip && subtitle) {
      return (
        <Tooltip>
          <TooltipTrigger asChild>{navContent}</TooltipTrigger>
          <TooltipContent className={tiers.tooltip}>
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
