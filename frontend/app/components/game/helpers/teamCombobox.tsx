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
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '~/components/ui/popover';
import type { TeamType } from '~/index';
import { cn } from '~/lib/utils';
interface Props {
  teams: TeamType[];
  selectedTeam: number;
  setSelectedTeam: React.Dispatch<React.SetStateAction<number>>;
}

import { getLogger } from '~/lib/logger';
const log = getLogger('TeamComboBox');
interface TeamComboBoxType {
  label: string;
  value: number | string;
}

export const TeamComboBox: React.FC<Props> = ({
  teams,
  selectedTeam,
  setSelectedTeam,
}) => {
  const isDesktop = useMediaQuery('(min-width: 768px)');

  const [open, setOpen] = React.useState(false);
  const getDropboxValues = () => {
    const comboBox: TeamComboBoxType[] = [];
    let team: any;
    teams.forEach((value: TeamType) => {
      comboBox.push({
        label: value.captain?.username || '',
        value: value.pk || 0,
      });
    });

    log.debug(comboBox);

    return comboBox;
  };
  const onChoose = (currentValue: string) => {
    setSelectedTeam(
      parseInt(currentValue) === selectedTeam ? 0 : parseInt(currentValue),
    );
    setOpen(false);
    log.debug(currentValue);
  };
  if (isDesktop) {
    return (
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button
            variant="outline"
            role="combobox"
            aria-expanded={open}
            className="w-[200px] justify-between"
          >
            {selectedTeam
              ? getDropboxValues().find(
                  (teaminfo: TeamComboBoxType) =>
                    teaminfo.value === selectedTeam,
                )?.label
              : 'Select Team ...'}
            <ChevronsUpDown className="opacity-50 z-900" />
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-[200px] p-0">
          <Command>
            <CommandInput placeholder="Search framework..." className="h-9" />
            <CommandList>
              <CommandEmpty>No framework found.</CommandEmpty>
              <CommandGroup>
                {getDropboxValues().map((framework) => (
                  <CommandItem
                    className="z-50"
                    key={framework.value}
                    value={framework.value.toString()}
                    onSelect={(currentValue) => onChoose(currentValue)}
                  >
                    {framework.label}
                    <Check
                      className={cn(
                        'ml-auto',
                        selectedTeam === framework.value
                          ? 'opacity-100'
                          : 'opacity-0',
                      )}
                    />
                  </CommandItem>
                ))}
              </CommandGroup>
            </CommandList>
          </Command>
        </PopoverContent>
      </Popover>
    );
  }

  return <div>Mobile not supported</div>;

  // <Drawer open={open} onOpenChange={setOpen}>
  //   <DrawerTrigger asChild>
  //     <Button variant="outline" className="w-[150px] justify-start">
  //       {selectedStatus ? <>{selectedStatus.label}</> : <>+ Set status</>}
  //     </Button>
  //   </DrawerTrigger>
  //   <DrawerContent>
  //     <div className="mt-4 border-t">
  //       <StatusList setOpen={setOpen} setSelectedStatus={setSelectedStatus} />
  //     </div>
  //   </DrawerContent>
  // </Drawer>
};
