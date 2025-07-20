## Building and Pushing Docker Images (using paths.py)

This project provides a `paths.py` utility to help manage Docker image tags and paths for backend, frontend, and nginx.

### 1. Authenticate to GitHub Container Registry

See the section above for Docker login instructions.

### 2. Build Docker Images

You can use the Dockerfiles and tags defined in `paths.py` to build images:

```sh
# Example for backend
docker build -f backend/Dockerfile -t ghcr.io/dtx-dota/website/backend .

# Example for frontend
docker build -f frontend/Dockerfile -t ghcr.io/dtx-dota/website/frontend .

# Example for nginx
docker build -f nginx/Dockerfile -t ghcr.io/dtx-dota/website/nginx .
```

### 3. Push Docker Images

```sh
docker push ghcr.io/dtx-dota/website/backend
docker push ghcr.io/dtx-dota/website/frontend
docker push ghcr.io/dtx-dota/website/nginx
```

### 4. Using the invoke script

If you have an invoke or tasks.py script for automation, you can run:

```sh
invoke build
invoke push
```

Or, if using Python directly:

```sh
python paths.py  # (if you have CLI logic in paths.py)
```

Refer to your `paths.py` for tag and path variables to use in your scripts or CI/CD.

---
---

## Publishing Docker Images to GitHub Container Registry

To push Docker images to a private GitHub Container Registry (ghcr.io):

1. **Authenticate to GitHub Container Registry:**
   - Create a GitHub Personal Access Token (PAT) with `write:packages` and `read:packages` scopes.
   - Login to the registry:

     ```sh
     echo YOUR_GITHUB_PAT | docker login ghcr.io -u YOUR_GITHUB_USERNAME --password-stdin
     ```

2. **Tag your Docker image:**

     ```sh
     docker tag local-image:tag ghcr.io/OWNER/REPO/IMAGE_NAME:TAG
     ```
     - `OWNER` is your GitHub username or org.
     - `REPO` is the repository name.
     - `IMAGE_NAME` is the image name (can be same as repo or custom).
     - `TAG` is the version/tag.

3. **Push the image:**

     ```sh
     docker push ghcr.io/OWNER/REPO/IMAGE_NAME:TAG
     ```

**Example:**

```sh
# 1. Login
echo ghp_abc123... | docker login ghcr.io -u myusername --password-stdin

# 2. Tag
docker tag myapp:latest ghcr.io/myusername/myrepo/myapp:latest

# 3. Push
docker push ghcr.io/myusername/myrepo/myapp:latest
```

---
# React + TypeScript + Vite

This template provides a minimal setup to get React working in Vite with HMR and some ESLint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react/README.md) uses [Babel](https://babeljs.io/) for Fast Refresh
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react-swc) uses [SWC](https://swc.rs/) for Fast Refresh

## Expanding the ESLint configuration

If you are developing a production application, we recommend updating the configuration to enable type-aware lint rules:

```js
export default tseslint.config({
  extends: [
    // Remove ...tseslint.configs.recommended and replace with this
    ...tseslint.configs.recommendedTypeChecked,
    // Alternatively, use this for stricter rules
    ...tseslint.configs.strictTypeChecked,
    // Optionally, add this for stylistic rules
    ...tseslint.configs.stylisticTypeChecked,
  ],
  languageOptions: {
    // other options...
    parserOptions: {
      project: ['./tsconfig.node.json', './tsconfig.app.json'],
      tsconfigRootDir: import.meta.dirname,
    },
  },
})
```

You can also install [eslint-plugin-react-x](https://github.com/Rel1cx/eslint-react/tree/main/packages/plugins/eslint-plugin-react-x) and [eslint-plugin-react-dom](https://github.com/Rel1cx/eslint-react/tree/main/packages/plugins/eslint-plugin-react-dom) for React-specific lint rules:

```js
// eslint.config.js
import reactX from 'eslint-plugin-react-x'
import reactDom from 'eslint-plugin-react-dom'

export default tseslint.config({
  plugins: {
    // Add the react-x and react-dom plugins
    'react-x': reactX,
    'react-dom': reactDom,
  },
  rules: {
    // other rules...
    // Enable its recommended typescript rules
    ...reactX.configs['recommended-typescript'].rules,
    ...reactDom.configs.recommended.rules,
  },
})
```
