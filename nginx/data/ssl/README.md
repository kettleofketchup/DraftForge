# This is for local development

Self-signed cert for the dev and test stacks. It covers `localhost`, `*.localhost`,
`s1.localhost` through `s9.localhost` (test stack slots) and `nginx`. Add `cert.crt` to
your browser to test https locally. Regenerate it with `./gen_cert.sh`, which keeps
`cert.key`.
