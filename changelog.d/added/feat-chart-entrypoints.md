- **Helm chart 0.2.0: several Traefik entry points.** `ingress.entryPoints` takes a
  list of entry points for the IngressRoute, for example a LAN entry point and a
  tunnel entry point, with the same middlewares on each. The single
  `ingress.entryPoint` still works when the list is empty. See `helm/README.md`.
