# The official digline image: the CLI, the three provider plugins, and nothing
# else. What it promises and what it deliberately does not is in README.md
# beside this file.
#
# The build context is *this directory*, not the repository root — nothing is
# copied in, every byte of the image comes from PyPI, and a small context keeps
# the daemon from being handed a checkout with a virtualenv in it:
#
#     docker build docker/ -t digline:local
#
# `await_index.py` beside this file is read during the build through a bind
# mount and never lands in a layer. It is a byte-for-byte copy of
# `.github/await_index.py`, and `tests/test_docker.py` holds the two identical.
# Pinned by digest, not by tag: `python:3.12-slim` is a moving target, and an
# image that cannot say which base it was built on cannot answer the one
# question an advisory asks. The digest is the multi-arch index, so the amd64
# and arm64 builds both resolve from it. Dependabot opens the bump — the tag in
# the comment is what a human reads, the digest is what the build obeys.
FROM python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea

# The versions are written here and nowhere else. `tests/test_docker.py` holds
# them to the versions this workspace declares, and the publishing workflow
# reads the tags back out of this file rather than repeating them — so an image
# that lags a release fails in the repository, before anything reaches a
# registry.
ARG DIGLINE_VERSION=0.16.0
ARG DIGLINE_ANTHROPIC_VERSION=0.5.2
ARG DIGLINE_OPENAI_VERSION=0.5.1
ARG DIGLINE_BEDROCK_VERSION=0.5.1

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

# How long to wait, from inside this build, for the index to serve the four
# pins below. **0 — the default — waits for nothing**, so a local
# `docker build` behaves exactly as it always did. The release and CI builds
# pass a timeout.
#
# Why here and not only on the runner: the runner-side wait in both workflows
# ran and passed, and `pip` then failed 16–20s later inside the build, served
# the previous version as the newest — on two releases in a row. The build
# resolves from its own network namespace, which can reach a different PyPI edge
# from the runner's, so a wait that polls one edge does not protect a consumer
# that polls another. The wait therefore runs in the same step as the install,
# from the same container, and fails by naming the exact version this consumer
# was not served.
ARG AWAIT_INDEX_TIMEOUT=0

# Into the system site-packages rather than a virtualenv: a suite with its own
# dependencies derives this image and installs them with `pip install`, and
# they have to land where digline already is.
#
# One `RUN` for the wait and the install, so a cached install can never be
# separated from the wait that protected it.
RUN --mount=type=bind,source=await_index.py,target=/tmp/await_index.py \
    if [ "${AWAIT_INDEX_TIMEOUT}" != "0" ]; then \
      TIMEOUT="${AWAIT_INDEX_TIMEOUT}" INTERVAL=15 python3 /tmp/await_index.py \
        "digline==${DIGLINE_VERSION}" \
        "digline-anthropic==${DIGLINE_ANTHROPIC_VERSION}" \
        "digline-openai==${DIGLINE_OPENAI_VERSION}" \
        "digline-bedrock==${DIGLINE_BEDROCK_VERSION}"; \
    fi \
 && pip install --no-cache-dir \
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
# So that a bare `docker run ghcr.io/digline/digline` says what it is
# instead of an argparse usage line and exit 2.
CMD ["--help"]
