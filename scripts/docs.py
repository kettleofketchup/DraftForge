from invoke.collection import Collection
from invoke.tasks import task

import paths

ns_docs = Collection("docs")


@task
def serve(c):
    """Start MkDocs development server with hot reload."""
    with c.cd(paths.PROJECT_PATH):
        c.run("mkdocs serve", pty=True)


@task
def build(c):
    """Build static documentation site."""
    with c.cd(paths.PROJECT_PATH):
        c.run("mkdocs build")


ns_docs.add_task(serve, name="serve")
ns_docs.add_task(build, name="build")
