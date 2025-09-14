import * as React from 'react';
import { memo } from 'react';
import { useUserStore } from '../../store/userStore';
import type { UserType } from '../user/types';
import { LoginWithDiscordButton } from './login';

const dtxLogo = () => {
  return (
    <a className="p-4" href="/">
      <div className="avatar avatar-placeholder">
        <div className="bg-blue-950 shadow text-neutral-content w-12 rounded-full">
          <span>DTX</span>
        </div>
      </div>
    </a>
  );
};

type Props = {
  user: UserType;
};

const menuItems = () => {
  const currentUser = useUserStore((state) => state.currentUser);
  return (
    <>
      <li>
        <a href="/about">About us</a>
      </li>
      <li>
        <a href="/tournaments" className="z-auto">
          {' '}
          Tournaments
        </a>
      </li>

      <li>
        <a href="/users">Users</a>
      </li>
      {currentUser?.is_staff && (
        <>
          <li>
            <a href="/admin">Admin</a>
          </li>
        </>
      )}
    </>
  );
};
export const ResponsiveAppBar: React.FC = memo(() => {
  const currentUser = useUserStore((state) => state.currentUser); // Zustand setter

  const dropdown = () => {
    return (
      <div className="dropdown">
        <div tabIndex={0} role="button" className="btn btn-ghost lg:hidden">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            className="h-5 w-5"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth="2"
              d="M4 6h16M4 12h8m-8 6h16"
            />
          </svg>
        </div>
        <ul
          tabIndex={0}
          className="menu menu-sm dropdown-content bg-base-100 rounded-box z-1 mt-3 w-52 p-2 shadow"
        >
          {menuItems()}
        </ul>
      </div>
    );
  };

  const menu = () => {
    return (
      <div className="navbar-center hidden lg:flex">
        <ul className="menu menu-horizontal px-1">{menuItems()}</ul>
      </div>
    );
  };

  return (
    <React.Suspense>
      <div className=" sticky z-50 top-0 navbar bg-base-100 shadow-sm p-0">
        <div className="navbar-start">
          {dropdown()}
          {dtxLogo()}
        </div>
        {menu()}

        <div className="navbar-end">
          <LoginWithDiscordButton />
        </div>
      </div>
    </React.Suspense>
  );
});
export default ResponsiveAppBar;
