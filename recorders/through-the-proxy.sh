#!/usr/bin/env bash
# The CI job `through-the-proxy`, runnable by hand from the repository's root
# once `uv sync --all-packages`, `npm ci --prefix recorders/node` and a JDK 21
# with Maven are there:
#
#     recorders/through-the-proxy.sh DIRECTORY
#
# The fake OpenAI and Anthropic of tests/test_record_proxy.py, as a process;
# `digline record proxy` in front of it, writing under DIRECTORY; then Node's,
# Java's and Python's SDKs, each a single call and a stream, sent through it
# with the base URL and X-Digline-Suite; Node's Bedrock client too, its two
# streams, which the upstream answers with the bytes of
# recorders/fixtures/eventstream/; Node's again with the recorder in the
# process, straight to the upstream, writing beside the proxy; then the proxy
# stopped, so its open episodes and its counts are written.
# tests/test_through_the_proxy.py reads what both wrote. Each step says how
# long it took.
set -euo pipefail

root="$1"
mkdir -p "$root"
python=.venv/bin/python
upstream_port=18790
proxy_port=18791

step() {
  local started=$SECONDS
  echo "::group::$1"
  shift
  "$@"
  echo "::endgroup::"
  echo "$((SECONDS - started)) s"
}

"$python" -m tests.proxy_upstream "$upstream_port" > "$root/upstream.log" 2>&1 &
upstream=$!
proxy=
# Both stopped however the script ends: a step that fails must not leave the
# proxy holding its port.
trap 'kill "$upstream"; if [ -n "$proxy" ]; then kill "$proxy"; fi' EXIT

# This machine's AWS credentials, as far as Bedrock's client and the proxy
# know: these, and no file. The proxy refuses a call signed with another key,
# and signs it again with these; they reach only the fake upstream.
export AWS_ACCESS_KEY_ID=AKIDPROXY AWS_SECRET_ACCESS_KEY=proxy-secret \
  AWS_REGION=us-east-1 AWS_DEFAULT_REGION=us-east-1 \
  AWS_CONFIG_FILE=/dev/null AWS_SHARED_CREDENTIALS_FILE=/dev/null \
  AWS_EC2_METADATA_DISABLED=true

DIGLINE_RECORD=1 .venv/bin/digline record proxy --root "$root" --tenant t \
  --port "$proxy_port" --episode-idle 600 \
  --upstream "openai=http://127.0.0.1:$upstream_port/v1" \
  --upstream "anthropic=http://127.0.0.1:$upstream_port" \
  --upstream "bedrock=http://127.0.0.1:$upstream_port" \
  > "$root/proxy.log" 2>&1 &
proxy=$!

ready=
for _ in $(seq 150); do
  if grep -q "point the SDK here" "$root/proxy.log"; then ready=1; break; fi
  sleep 0.2
done
cat "$root/proxy.log"
if [ -z "$ready" ]; then
  echo "the proxy did not start within 30 s"
  exit 1
fi
export DIGLINE_PROXY="http://127.0.0.1:$proxy_port"

step "Node: openai and @anthropic-ai/sdk" env ANTHROPIC_BASE_URL="$DIGLINE_PROXY" node recorders/node/through-the-proxy.mjs
step "Node: the recorder in the process, straight to the upstream" env DIGLINE_RECORD=1 DIGLINE_ROOT="$root" DIGLINE_UPSTREAM="http://127.0.0.1:$upstream_port" node recorders/node/in-process.mjs
step "Java: LangChain4j OpenAI" mvn -B -q -f recorders/java-proxy/pom.xml test "-Ddigline.proxy=$DIGLINE_PROXY"
step "Python: openai and anthropic, the control" "$python" recorders/python-proxy/through_the_proxy.py

kill -TERM "$proxy"
wait "$proxy"
proxy=
cat "$root/proxy.log"
