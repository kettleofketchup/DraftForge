import {
  type ComponentPropsWithoutRef,
  createContext,
  useContext,
  useMemo,
} from 'react';
import ReactMarkdown, {
  type Components,
  type ExtraProps,
} from 'react-markdown';
import { cn } from '~/lib/utils';

type HeadingTag = 'h1' | 'h2' | 'h3' | 'h4' | 'h5' | 'h6';

const HEADING_CLASS: Record<HeadingTag, string> = {
  h1: 'text-xl font-bold text-foreground',
  h2: 'text-lg font-semibold text-foreground',
  h3: 'text-base font-semibold text-foreground',
  h4: 'text-sm font-semibold text-foreground',
  h5: 'text-sm font-medium text-muted-foreground',
  h6: 'text-xs font-medium uppercase text-muted-foreground',
};

const EXTERNAL_LINK = /^https?:\/\//i;

const InCodeBlock = createContext(false);

function Code({
  node: _node,
  className,
  ...props
}: ComponentPropsWithoutRef<'code'> & ExtraProps) {
  const block = useContext(InCodeBlock);
  return (
    <code
      className={cn(
        'font-mono text-xs',
        !block && 'bg-muted rounded px-1 break-all',
        className,
      )}
      {...props}
    />
  );
}

function headingTag(level: number, offset: number): HeadingTag {
  return `h${Math.min(6, Math.max(1, level + offset))}` as HeadingTag;
}

function buildComponents(headingOffset: number): Components {
  const heading = (level: number) =>
    function Heading({
      node: _node,
      className,
      ...props
    }: ComponentPropsWithoutRef<'h1'> & ExtraProps) {
      const Tag = headingTag(level, headingOffset);
      return <Tag className={cn(HEADING_CLASS[Tag], className)} {...props} />;
    };

  return {
    h1: heading(1),
    h2: heading(2),
    h3: heading(3),
    h4: heading(4),
    h5: heading(5),
    h6: heading(6),
    p: ({ node: _node, ...props }) => (
      <p className="text-foreground" {...props} />
    ),
    ul: ({ node: _node, ...props }) => (
      <ul className="list-disc pl-5 flex flex-col gap-1" {...props} />
    ),
    ol: ({ node: _node, ...props }) => (
      <ol className="list-decimal pl-5 flex flex-col gap-1" {...props} />
    ),
    li: ({ node: _node, ...props }) => (
      <li className="text-foreground" {...props} />
    ),
    a: ({ node: _node, href, ...props }) => {
      const external = href !== undefined && EXTERNAL_LINK.test(href);
      return (
        <a
          href={href}
          className="text-primary underline [overflow-wrap:anywhere]"
          {...(external
            ? { target: '_blank', rel: 'noopener noreferrer' }
            : {})}
          {...props}
        />
      );
    },
    pre: ({ node: _node, ...props }) => (
      <InCodeBlock.Provider value={true}>
        <pre
          className="bg-muted rounded p-2 whitespace-pre-wrap [overflow-wrap:anywhere]"
          {...props}
        />
      </InCodeBlock.Provider>
    ),
    code: Code,
  };
}

export function ChangelogMarkdown({
  markdown,
  headingOffset,
}: {
  markdown: string;
  headingOffset: number;
}): React.JSX.Element {
  const components = useMemo(
    () => buildComponents(headingOffset),
    [headingOffset],
  );
  return (
    <div className="flex flex-col gap-2 text-sm text-foreground">
      <ReactMarkdown skipHtml components={components}>
        {markdown}
      </ReactMarkdown>
    </div>
  );
}
