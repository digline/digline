# The official digline image: the CLI, the three provider plugins, and nothing
# else. What it promises and what it deliberately does not is in README.md
# beside this file.
#
# The build context is *this directory*, not the repository root — nothing is
# copied in, every byte comes from PyPI, and a one-file context keeps the
# daemon from being handed a checkout with a virtualenv in it:
#
#     docker build docker/ -t digline:local
FROM python:3.12-slim

# The versions are written here and nowhere else. `tests/test_docker.py` holds
# them to the versions this workspace declares, and the publishing workflow
# reads the tags back out of this file rather than repeating them — so an image
# that lags a release fails in the repository, before anything reaches a
# registry.
ARG DIGLINE_VERSION=0.4.0
ARG DIGLINE_ANTHROPIC_VERSION=0.2.0
ARG DIGLINE_OPENAI_VERSION=0.2.0
ARG DIGLINE_BEDROCK_VERSION=0.2.0

# Passed by the workflow, empty on a local build. Empty is the honest value: a
# revision label that names a commit the image was not built from is worse than
# one that is absent.
ARG VCS_REF=""

LABEL org.opencontainers.image.title="digline"
LABEL org.opencontainers.image.description="Regression testing for LLM output, against a baseline committed in your own repo."
LABEL org.opencontainers.image.source="https://github.com/digline/digline"
LABEL org.opencontainers.image.version="${DIGLINE_VERSION}"
LABEL org.opencontainers.image.revision="${VCS_REF}"
LABEL org.opencontainers.image.licenses="Apache-2.0"

# A run records the commit it was produced from, and that field is half of what
# a report shows a reader: "tested under which commit". Without git in the
# image it is silently `null` on every run — the CLI treats being outside a
# repository as normal, which is right, and here it would be wrong.
#
# `safe.directory '*'` because the repository arrives as a bind mount owned by
# whoever owns it on the host, which is not the container's user. git refuses a
# tree it considers someone else's, `git_commit()` reads that refusal as "no
# commit", and the run loses the field with nothing said. The scope of the
# blanket is one container that already has the whole tree mounted into it.
RUN apt-get update \
 && apt-get install --yes --no-install-recommends git \
 && rm -rf /var/lib/apt/lists/* \
 && git config --system --add safe.directory '*'

# Into the system site-packages rather than a virtualenv: a suite with its own
# dependencies derives this image and installs them with `pip install`, and
# they have to land where digline already is.
RUN pip install --no-cache-dir \
      "digline==${DIGLINE_VERSION}" \
      "digline-anthropic==${DIGLINE_ANTHROPIC_VERSION}" \
      "digline-openai==${DIGLINE_OPENAI_VERSION}" \
      "digline-bedrock==${DIGLINE_BEDROCK_VERSION}" \
 && digline --help > /dev/null

# The suite is imported from the mounted repository, so the bytecode Python
# would write for it lands in the *user's* tree, under whatever uid the
# container runs as. A cache directory nobody asked for and half of them cannot
# delete is not a thing to leave behind.
ENV PYTHONDONTWRITEBYTECODE=1

# Non-root. `--user "$(id -u)"` overrides this where the mounted repository is
# owned by another uid; README.md beside this file says when and why.
RUN groupadd --gid 1000 digline \
 && useradd --uid 1000 --gid 1000 --create-home digline \
 && mkdir -p /work \
 && chown digline:digline /work
USER digline

# `.digline/` belongs to the repository, never to the image: the repository is
# mounted here, and everything the run writes is written into it.
WORKDIR /work

ENTRYPOINT ["digline"]
# So that a bare `docker run ghcr.io/digline/digline:0.4.0` says what it is
# instead of an argparse usage line and exit 2.
CMD ["--help"]
