#!/usr/bin/env bash
# The four versions the image installs, as pip pins, read out of the one file
# that decides them.
#
#   docker_pins.sh [dockerfile]  ->  digline==0.13.1
#                                    digline-anthropic==0.5.0
#                                    digline-openai==0.5.0
#                                    digline-bedrock==0.5.0
#
# Two callers wait on these before building — `docker-publish.yml` at release
# and the `image` job in `ci.yml` — and a version number written twice is a
# version number that will one day disagree with itself. `docker/Dockerfile`
# holds it once; this reads it back.
#
# The core alone is not enough, and that is what this exists for: the wait that
# `docker-publish.yml` used to do asked only about `digline`, while the image
# also pins the three plugins. On digline-openai-v0.5.0 the build was served
# `digline-anthropic` only up to 0.4.0 — the core was there, a plugin was not,
# and nothing had asked.
set -euo pipefail

dockerfile=${1:-docker/Dockerfile}

[ -f "$dockerfile" ] || {
  echo "::error title=No Dockerfile to read::$dockerfile does not exist" >&2
  exit 1
}

while read -r arg package; do
  [ -n "$arg" ] || continue
  version=$(sed -n "s/^ARG ${arg}=//p" "$dockerfile")
  if [ -z "$version" ]; then
    # An empty version would become the pin `digline==`, which waits for a file
    # that cannot exist and fails thirty minutes later for the wrong reason.
    echo "::error title=$dockerfile declares no ARG $arg::the image's pins" \
         "cannot be derived, so nothing can be waited for" >&2
    exit 1
  fi
  echo "${package}==${version}"
done <<'ARGS'
DIGLINE_VERSION digline
DIGLINE_ANTHROPIC_VERSION digline-anthropic
DIGLINE_OPENAI_VERSION digline-openai
DIGLINE_BEDROCK_VERSION digline-bedrock
ARGS
