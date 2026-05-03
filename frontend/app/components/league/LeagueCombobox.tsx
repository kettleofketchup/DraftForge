'use client';

import { useMediaQuery } from '@uidotdev/usehooks';
import { Check, ChevronsUpDown } from 'lucide-react';
import * as React from 'react';

import { Button } from '~/components/ui/button';
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from '~/components/ui/command';
import { useLeagues } from '~/components/league/hooks/useLeagues';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '~/components/ui/popover';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '~/components/ui/select';
import { cn } from '~/lib/utils';

export interface LeagueComboboxProps {
  organizationId: number | undefined;
  value: number | null;
  onChange: (value: number | null) => void;
  disabled?: boolean;
  placeholder?: string;
  className?: string;
  id?: string;
  invalid?: boolean;
  /** data-testid to apply to the trigger (preserves existing test-ids) */
  triggerTestId?: string;
  /** prefix for per-item data-testids: `${itemTestIdPrefix}${leagueId}` */
  itemTestIdPrefix?: string;
  /** data-testid for the search input (desktop only) */
  searchTestId?: string;
  /** data-testid for the Clear-selection item (desktop) and No-league sentinel (mobile) */
  clearTestId?: string;
}

export const LeagueCombobox: React.FC<LeagueComboboxProps> = ({
  organizationId,
  value,
  onChange,
  disabled,
  placeholder = 'Select league…',
  className,
  id,
  invalid,
  triggerTestId,
  itemTestIdPrefix,
  searchTestId,
  clearTestId,
}) => {
  const [open, setOpen] = React.useState(false);
  const { leagues, isLoading } = useLeagues(organizationId);
  const isDesktop = useMediaQuery('(min-width: 768px)');

  const selected = value != null ? leagues.find((l) => l.pk === value) : null;
  const isOrgMissing = organizationId == null;
  const triggerDisabled = disabled || isOrgMissing;

  if (!isDesktop) {
    const noLeagues = !isLoading && leagues.length === 0;
    return (
      <Select
        value={value != null ? String(value) : ''}
        onValueChange={(v) => {
          if (v === '__clear__') {
            onChange(null);
          } else {
            onChange(parseInt(v, 10));
          }
        }}
        disabled={triggerDisabled || noLeagues}
      >
        <SelectTrigger
          id={id}
          data-testid={triggerTestId}
          aria-invalid={invalid || undefined}
          className={cn('w-full', className)}
        >
          <SelectValue
            placeholder={
              isLoading
                ? 'Loading leagues…'
                : noLeagues
                  ? 'No leagues in this organization'
                  : placeholder
            }
          />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="__clear__" data-testid={clearTestId}>
            — No league —
          </SelectItem>
          {leagues.map((league) => (
            <SelectItem
              key={league.pk}
              value={String(league.pk)}
              data-testid={
                itemTestIdPrefix ? `${itemTestIdPrefix}${league.pk}` : undefined
              }
            >
              {league.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    );
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          id={id}
          variant="outline"
          role="combobox"
          aria-expanded={open}
          aria-invalid={invalid || undefined}
          disabled={triggerDisabled}
          data-testid={triggerTestId}
          className={cn('w-full justify-between', className)}
        >
          <span className="truncate">
            {selected ? selected.name : placeholder}
          </span>
          <ChevronsUpDown className="opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-(--radix-popover-trigger-width) p-0">
        <Command>
          <CommandInput
            placeholder="Search leagues…"
            className="h-9"
            data-testid={searchTestId}
          />
          <CommandList>
            <CommandEmpty>
              {isLoading
                ? 'Loading leagues…'
                : leagues.length === 0
                  ? 'No leagues in this organization'
                  : 'No leagues match your search'}
            </CommandEmpty>
            {leagues.length > 0 && (
              <CommandGroup>
                {leagues.map((league) => (
                  <CommandItem
                    key={league.pk}
                    value={league.name}
                    data-testid={
                      itemTestIdPrefix ? `${itemTestIdPrefix}${league.pk}` : undefined
                    }
                    onSelect={() => {
                      onChange(league.pk);
                      setOpen(false);
                    }}
                  >
                    {league.name}
                    <Check
                      className={cn(
                        'ml-auto',
                        value === league.pk ? 'opacity-100' : 'opacity-0',
                      )}
                    />
                  </CommandItem>
                ))}
              </CommandGroup>
            )}
            {value !== null && (
              <CommandGroup>
                <CommandItem
                  value="__clear__"
                  data-testid={clearTestId}
                  onSelect={() => {
                    onChange(null);
                    setOpen(false);
                  }}
                >
                  — Clear selection —
                </CommandItem>
              </CommandGroup>
            )}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
};

export default LeagueCombobox;
