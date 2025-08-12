to run python, you have to source .venv/bin/activate
# Project Goal
Website that provides a way to help manage DTX, a Dota2 gaming organization.


# Project Structure

## Backend
- folder location within repo: ./backend/

###
### Stack
- django
- django rest framework
-  django-social-auth
    - oauth integration: discord
- Discord app and api

## Frontend

- folder location within repo: ./frontend/

### Stack
- React
- react-router-dom
- styling: tailwindcss
- components: daisyui and headlessui


# Project coding standards


## TypeScript Guidelines
- Use TypeScript for all new code
- Follow functional programming principles where possible
- Use interfaces for data structures and type definitions
- Prefer immutable data (const, readonly)
- Use optional chaining (?.) and nullish coalescing (??) operators

## React Guidelines
- Use functional components with hooks
- Follow the React hooks rules (no conditional hooks)
- Use React.FC type for components with children
- Keep components small and focused
- Use CSS modules for component styling

## Naming Conventions
- Use PascalCase for component names, interfaces, and type aliases
- Use camelCase for variables, functions, and methods
- Prefix private class members with underscore (_)
- Use ALL_CAPS for constants

## Error Handling
- Use try/catch blocks for async operations
- Implement proper error boundaries in React components
- Always log errors with contextual information

## Frontend Logging Guidelines

- Use the `getLogger` function to create a logger instance for each module named log
    - Example: `import {getLogger} from '~/index'; const log = getLogger('<moduleName>');`
- Frontend: Log messages should include the module name for context
- Frontend: Use appropriate log levels (debug, info, warn, error)
- Frontend:  Avoid logging sensitive information (e.g., passwords, tokens)
- Frontend: Use structured logging where possible (e.g., JSON format)
- Frontend: Use `log.debug` for detailed debugging information
- Frontend: Use `log.info` for general information messages
- Frontend: Use `log.warn` for warnings that do not require immediate attention
- Frontend: Use `log.error` for error messages that require attention




# Steam API


Python: SteamAPI callers in python to parse steamapi for dota games. This will be stored in a Django cache to ensure rate limiting and the typescript will only ever call the Django endpoints

typescript: some library with that has the steamapi types to parse steamapi json from the backend.

Other use cases involving steam api include:
- searching for a steamid from a username
- searching for games involving a users in the dtx dota guild
- searching for live stats of active dota games involving people

Type script/frontend side only get steamapi data from the python. Only python does the calling.

With this information what libraries handle a lot of this info. Please provide with last update and last 6 month commit history for the project
