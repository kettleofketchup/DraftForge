/**
 * User search input with debounced search and dropdown.
 * Searches by Discord username/nickname.
 */

import { useState, useCallback, useRef, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Search, Loader2 } from 'lucide-react';
import type { UserType } from '~/components/user/types';
import { searchUsers } from '~/components/api/api';
import { useDebouncedValue } from '~/hooks/useDebouncedValue';

interface UserSearchInputProps {
  onSelect: (user: UserType) => void;
  placeholder?: string;
  isLoading?: boolean;
  excludeIds?: number[];
}

export function UserSearchInput({
  onSelect,
  placeholder = 'Search users...',
  isLoading = false,
  excludeIds = [],
}: UserSearchInputProps) {
  const [query, setQuery] = useState('');
  const [isOpen, setIsOpen] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const debouncedQuery = useDebouncedValue(query, 300);

  // Search query
  const { data: searchResults, isFetching } = useQuery({
    queryKey: ['userSearch', debouncedQuery],
    queryFn: () => searchUsers(debouncedQuery),
    enabled: debouncedQuery.length >= 3,
  });

  // Filter out excluded users
  const filteredResults =
    searchResults?.filter((user) => user.pk && !excludeIds.includes(user.pk)) || [];

  // Handle click outside to close dropdown
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(event.target as Node) &&
        inputRef.current &&
        !inputRef.current.contains(event.target as Node)
      ) {
        setIsOpen(false);
      }
    }

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleSelect = useCallback(
    (user: UserType) => {
      onSelect(user);
      setQuery('');
      setIsOpen(false);
    },
    [onSelect]
  );

  const showDropdown = isOpen && query.length >= 3;

  return (
    <div className="relative">
      <div className="relative">
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setIsOpen(true);
          }}
          onFocus={() => setIsOpen(true)}
          placeholder={placeholder}
          className="input input-bordered w-full pl-10 pr-4"
          disabled={isLoading}
        />
        <div className="absolute left-3 top-1/2 -translate-y-1/2">
          {isFetching || isLoading ? (
            <Loader2 className="h-4 w-4 animate-spin text-gray-400" />
          ) : (
            <Search className="h-4 w-4 text-gray-400" />
          )}
        </div>
      </div>

      {/* Dropdown */}
      {showDropdown && (
        <div
          ref={dropdownRef}
          className="absolute z-50 w-full mt-1 bg-base-100 border border-base-300 rounded-lg shadow-lg max-h-60 overflow-y-auto"
        >
          {query.length < 3 ? (
            <div className="p-3 text-sm text-gray-500">Type at least 3 characters...</div>
          ) : isFetching ? (
            <div className="p-3 text-sm text-gray-500 flex items-center gap-2">
              <Loader2 className="h-4 w-4 animate-spin" />
              Searching...
            </div>
          ) : filteredResults.length === 0 ? (
            <div className="p-3 text-sm text-gray-500">No users found</div>
          ) : (
            <ul>
              {filteredResults.map((user) => {
                const displayName =
                  user.guildNickname ||
                  user.discordNickname ||
                  user.nickname ||
                  user.username;
                return (
                  <li key={user.pk}>
                    <button
                      onClick={() => handleSelect(user)}
                      className="w-full flex items-center gap-3 p-3 hover:bg-base-200 transition-colors text-left"
                    >
                      <img
                        src={user.avatarUrl || user.avatar || '/default-avatar.png'}
                        alt={displayName}
                        className="w-8 h-8 rounded-full"
                      />
                      <div>
                        <div className="font-medium">{displayName}</div>
                        {user.username && user.username !== displayName && (
                          <div className="text-sm text-gray-500">
                            @{user.username}
                          </div>
                        )}
                      </div>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
