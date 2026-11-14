import * as React from 'react';
import { Link } from 'react-router';
import { cn } from '~/lib/utils';
import { Tooltip, TooltipContent, TooltipTrigger } from '../ui/tooltip';

/**
 * NavItem layout tiers (above md/768px — below is the MobileNav drawer):
 *   - md → <1100px: icon only; subtitle in tooltip (showSubtitleTooltip).
 *   - 1100px → <2xl: icon + title inline, subtitle still tooltip-only.
 *   - 2xl+ (1536px): icon + title + inline subtitle stacked vertically.
 * Nine nav items fit horizontally below 2xl; stacking earlier overflows (#252).
 */
type NavItemBaseProps = {
  icon?: React.ReactNode;
  title: string;
  subtitle?: string;
  badge?: React.ReactNode;
  /** Shown after the text at every width, e.g. a dropdown chevron */
  indicator?: React.ReactNode;
  /** When true: hides text below 1100px, shows icons only with tooltip */
  hideTextOnSmall?: boolean;
  /** Show subtitle as tooltip on small screens (below xl) */
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
      hideTextOnSmall = false,
      showSubtitleTooltip = false,
      titleClassName,
      'data-testid': dataTestId,
    } = props;
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
            'flex min-w-0 items-center 2xl:flex-col 2xl:items-center',
            hideTextOnSmall && 'hidden min-[1100px]:flex',
          )}
        >
          <div className="flex items-center justify-center gap-1">
            <span
              className={cn(
                'text-xs font-bold leading-normal truncate text-center text-outline-sm text-[#646cff]',
                titleClassName,
              )}
            >
              {title}
            </span>
            {badge}
          </div>
          {subtitle && (
            <span className="text-[10px] text-text-muted leading-normal truncate hidden 2xl:block text-center">
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
        hideTextOnSmall: _hideTextOnSmall,
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
        hideTextOnSmall: _hideTextOnSmall,
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
          <TooltipContent className="2xl:hidden">
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
