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
