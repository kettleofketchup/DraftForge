## Building and Pushing Docker Images (using paths.py)

This project provides a `paths.py` utility to help manage Docker image tags and paths for backend, frontend, and nginx.

### 1. Authenticate to GitHub Container Registry

See the section above for Docker login instructions.

### 2. Build Docker Images

You can use the Dockerfiles and tags defined in `paths.py` to build images:

```sh
# Example for backend
inv docker.backend.build

# Example for frontend
inv docker.frontend.build

# Example for nginx
inv docker.nginx.build

#or

inv docker.all.build
```

### 3. Push Docker Images

```sh
# Example for backend
inv docker.backend.push

# Example for frontend
inv docker.frontend.push

# Example for nginx
inv docker.nginx.push

#or

inv docker.all.push
```

Refer to your `paths.py` for tag and path variables to use in your scripts or CI/CD.

and Update the pyproject.toml version as that will match the tag versions
---

# Update Version in docker compose

when you want to update the version for pyproject and docker ocmpose, run the following


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

### 1. Login

```sh
# 1. Login
echo <pat>... | docker login ghcr.io -u myusername --password-stdin
```


# 2. Tag
See building instructions above for building
Version is grabbed from pyproject.toml


# 3. Push
See pushing instructions above for building
Version is grabbed from pyproject.tom
```

---

# React + TypeScript + Vite

This template provides a minimal setup to get React working in Vite with HMR and some ESLint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react/README.md) uses [Babel](https://babeljs.io/) for Fast Refresh
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react-swc) uses [SWC](https://swc.rs/) for Fast Refresh


# Github action locally

act -W .github/workflows/test.yml -s GITHUB_TOKEN=<YOUR_H_TOKEN>
