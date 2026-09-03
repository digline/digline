# The official digline image

`ghcr.io/digline/digline`

The official image runs any suite that depends only on digline and its plugins
— the CI-gate case, HttpTarget against an external app. A suite with its own
dependencies derives the image: `FROM ghcr.io/digline/digline:<version>` +
install. No dynamic installs at runtime, ever.

That paragraph is the promise, and it is the whole of it. An image that
sometimes pip-installs what a suite turns out to need is an image whose
contents nobody can state, and a gate whose contents nobody can state is not a
gate.

## Usage

The repository is mounted; nothing of yours lives in the image:

```sh
docker run -v $PWD:/work ghcr.io/digline/digline:0.4.0 compare --suite eval/suite.py
```

`WORKDIR` is `/work` and the entrypoint is `digline`, so every argument after
the image name is the command line you would have typed locally — `run`,
`compare`, `promote`, `report`, `list`, `migrate`. The exit code is the answer:
`0` fine, `1` got worse, `2` could not be judged.

`.digline/` is written into the mounted repository, where it belongs:
`baselines/` for you to commit, `runs/` git-ignored through a `.gitignore`
digline writes. Nothing is kept in the image, and nothing outside `/work` is
written at all.

The whole cycle, from a checkout of your own repository:

```sh
digline() { docker run --rm -v "$PWD:/work" ghcr.io/digline/digline:0.4.0 "$@"; }

digline run     --suite eval/suite.py
digline promote --suite eval/suite.py --run latest
digline compare --suite eval/suite.py --run latest
```

## Tags

| Tag | |
|---|---|
| `0.4.0` | that version of digline, and the plugin versions it shipped with |
| `0.4` | the newest patch on that minor |
| `latest` | the newest release |

**Pin the exact version in CI.** A gate that silently changes what it runs is a
gate that will one day fail for a reason nobody can find, on a commit that
changed nothing. `latest` is for trying it out.

## When the volume is owned by someone else

The image runs as a non-root user, uid 1000. Where your repository is owned by
another uid — the ordinary case on Linux and in CI — the run cannot write
`.digline/` and fails on the first write. Say who you are:

```sh
docker run --user "$(id -u):$(id -g)" -v "$PWD:/work" ghcr.io/digline/digline:0.4.0 \
  run --suite eval/suite.py
```

Then the files that come back are yours, which is the point: a baseline you
have to `sudo chown` before you can commit it is a baseline you will not
commit. Docker Desktop on macOS and Windows maps the ownership for you and
neither flag is needed there.

## A suite with its own dependencies

Derive the image. Installing at build time is what keeps the promise above: the
image you tested is the image the gate runs.

```dockerfile
FROM ghcr.io/digline/digline:0.4.0

# The base image runs as uid 1000, which does not own the site-packages it
# would be installing into.
USER root
RUN pip install --no-cache-dir httpx==0.28.1 pandas==2.2.3
USER digline
```

`pip` resolves to the interpreter digline is installed in, so what you add is
importable from your suite with nothing else to configure.

## What is inside

- `python:3.12-slim`
- `digline`, and the three provider plugins — `digline-anthropic`,
  `digline-openai`, `digline-bedrock` — installed from PyPI at build time, at
  the versions pinned in the `Dockerfile` beside this file
- `git`, so that a run records the commit of the mounted repository. Without it
  that field is silently `null`, and "tested under which commit" is half of
  what a report shows a reader

No build tooling, no package index configured to be reached at runtime, no
agent, and no network call digline makes on its own — the ones your suite
configures, to your provider, are the only ones there are.

## Building it yourself

```sh
docker build docker/ -t digline:local          # the context is docker/: nothing is copied in
docker run --rm digline:local --help
```

Every version is a build argument, so an image against another release needs no
edit:

```sh
docker build docker/ -t digline:0.3.1 --build-arg DIGLINE_VERSION=0.3.1
```

## How it is published

`.github/workflows/docker-publish.yml`, by hand
(`gh workflow run docker-publish.yml --ref <branch>`). It builds for `amd64`
and `arm64`, runs the front page's quickstart inside the built image and checks
that the exit codes are the ones the README claims, and only then pushes to
GHCR with the repository's own `GITHUB_TOKEN`. The tags come from the
`Dockerfile`'s `DIGLINE_VERSION`; nothing repeats a version number.
