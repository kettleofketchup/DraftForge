import { useEffect, useState } from 'react'
import type { FormEvent } from 'react';
import type { User } from '~/components/user/types';
import  { UserCard } from '~/components/user/userCard';
import { useUsers } from '~/components/user/userUser';
import axios from "~/components/api/axios"
import { useUserStore } from '~/store/useUserStore';
import { Combobox, ComboboxInput, ComboboxOption, ComboboxOptions } from '@headlessui/react'
import Footer from '~/components/footer';

export function UsersPage() {
  const user:User = useUserStore((state) => state.user ); // Zustand setter
  const { users, loading, error, getUsers } = useUsers();
  const [anchorEl, setAnchorEl] = useState<HTMLElement | null>(null);

  const [selectedPerson, setSelectedPerson] = useState(null);
  const [query, setQuery] = useState('')

  const filteredUsers =
    query === ''
      ? users
      : users.filter((person) => {
          return person.username.toLowerCase().includes(query.toLowerCase())
        })


  const searchBar = () => {

    return (

      <div className='justify-self-top content-self-center align-middle '>

           { users && (

            <label className="input">
              <svg className="h-[1em] opacity-50" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
                <g
                  strokeLinejoin="round"
                  strokeLinecap="round"
                  strokeWidth="2.5"
                  fill="none"
                  stroke="currentColor"
                >
                  <circle cx="11" cy="11" r="8"></circle>
                  <path d="m21 21-4.3-4.3"></path>
                </g>
              </svg>
              <Combobox value={selectedPerson} onChange={setSelectedPerson} onClose={() => setQuery('')}>
                <ComboboxInput
                  aria-label="Assignee"
                  displayValue={(person:User) => person?.username}
                  onChange={(event) => setQuery(event.target.value)}
                />
                <ComboboxOptions anchor="bottom" className="border empty:invisible bg-base-100 shadow-lg rounded-lg mt-5">
                  {/* {filteredUsers && filteredUsers.map((person) => (
                    <ComboboxOption key={person.pk} value={person} className="data-focus:bg-purple-900">
                      {person.username}
                    </ComboboxOption>

                    ))} */}
                </ComboboxOptions>

              </Combobox>
            </label>

          )}
      </div>
        )
    }


  if (!user || !user.is_staff) return (

    <div className="flex justify-center h-full content-center mb-0 mt-0 p-0">
      <div className='justify-self-center content-center align-middle'>
        <span> You are not authorized to view this page</span>
      </div>
    </div>
  )
  useEffect(() => {

    getUsers();
  }, [] );

  useEffect(() => {
  }, [users] );

  const addUserBtn = () => {
    const newUser = () =>{
        return {
          username: "NewUser"
        } as User;
    }

    return (
      <>


        <label htmlFor="my_modal_7" className="btn outline outline-green-500 rounded-lg
          hover:bg-green-900/50
           hover:shadow-xl/10
             delay-10 duration-300 ease-in-out">Create User</label>

        <input type="checkbox" id="my_modal_7" className="modal-toggle" />
        <div className="modal" role="dialog">

          <div className="modal-box">
            <h3 className="text-lg font-bold">Hello!</h3>
            <UserCard user={newUser()} edit={true} saveFunc={"create"} key="modal_usercard"/>

            <p className="py-4">This modal works with a hidden checkbox!</p>
          </div>
          <label className="modal-backdrop" htmlFor="my_modal_7">Close</label>
        </div>
      </>
    )
  }


  return (
    <>
      <div className="flex flex-col items-start p-4 h-full  ">
        <div className="grid grid-flow-row-dense grid-auto-rows
        align-middle content-center justify-center
       grid-cols-4
         w-full ">
          <div className='flex'>
            {searchBar()}
            </div>
          <div className="flex col-start-4 align-end content-end justify-end">
            {addUserBtn()}
          </div>
        </div>
        <div className="grid grid-flow-row-dense grid-auto-rows
        align-middle content-center justify-center
         grid-cols-1 md:grid-cols-2 lg:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4
         mb-0 mt-0 p-0 bg-base-900  w-full">
          {filteredUsers?.map((u) => (
            <div className="grid" key={u.pk}>
              <UserCard user={u} />
            </div>
          ))}

        </div>
    </div>

    </>
  );

}
