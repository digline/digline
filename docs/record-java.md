# digline for Java

An application written in Java keeps the calls it makes to a model as
recordings, the files [`digline record`](record.md) turns into a suite's
cases. Which door it goes through depends on what makes the call:

| What makes the call | The door | How it was read |
|---|---|---|
| The official OpenAI Java SDK, the official Anthropic Java SDK, the AWS SDK v2 for Bedrock | **Two files copied into the project**, a writer and a hook for the client | run by `recorders/java`'s tests, on each SDK's real client against a fake provider on `127.0.0.1`: measured at the versions [ADR 0062](adr/0062-the-recorder-out-of-process-and-in-other-processes.md) read, and run by CI at those `recorders/java/pom.xml` names |
| LangChain4j, Quarkus-LangChain4j | **[`digline record proxy`](record.md#through-the-proxy-digline-record-proxy)**, with the base URL from configuration and the suite in a header or the path | LangChain4j with a header, single and streamed, run through the proxy by the CI job `through-the-proxy` on every pull request; Quarkus-LangChain4j by the path alone, run through the proxy for [ADR 0062](adr/0062-the-recorder-out-of-process-and-in-other-processes.md) on 2026-11-04 |
| Spring AI | not measured | no version of it was read |

Either way the files are the same, and so is everything downstream:
`digline record import`, `compare`, the page, a run. What a file holds is
[the recording document](recording-format.md).

No call to a provider was made for this page: the SDKs were run against fake
providers that answer in each provider's shape.

## Install the digline CLI

The commands on this page, `digline record on`, `status`, `import`, `proxy`,
`view` and `run`, are digline's command line, which is Python. In a project
that is not Python, install it as a tool of its own, apart from the project.

> **Arrives with digline 1.1.** The release on PyPI has no `digline record`,
> so until 1.1.0 is published the line below installs digline and its
> plugins from this repository.

```console
$ uv tool install "digline @ git+https://github.com/digline/digline" \
    --with "digline-openai @ git+https://github.com/digline/digline#subdirectory=packages/digline-openai" \
    --with "digline-anthropic @ git+https://github.com/digline/digline#subdirectory=packages/digline-anthropic" \
    --with "digline-bedrock @ git+https://github.com/digline/digline#subdirectory=packages/digline-bedrock"
```

Each `--with` adds the plugin of a provider that the proxy routes to or that
the suite's judge calls, and the ones you do not use can be left out. The
[Quickstart](https://github.com/digline/digline#quickstart) installs digline
into a Python project instead, with `uv add digline` or `pip install digline`,
and says which Python it needs. The line above was run on 2026-11-06, and
installed digline 1.1.0 from `main` at `98bbf62c`; `pipx` was not tried.

## With an official SDK: the files to copy

Copy the files your client's row names from
`recorders/java/src/main/java/dev/digline/` in digline's repository into your
project, in the package `dev.digline`. They need Java 21. The writer,
`DiglineRecorder.java`, and `DiglineMessages.java`, which reads Anthropic's
Messages for the two hooks that meet it, need the JDK alone, and each hook
needs only the SDK it hooks:

| Your client | The files to copy | How the hook is installed |
|---|---|---|
| `com.openai:openai-java`, or any OkHttp client calling Chat Completions | `DiglineRecorder.java`, `DiglineOkHttp.java` | `addInterceptor` on the client's builder |
| `com.anthropic:anthropic-java` | `DiglineRecorder.java`, `DiglineAnthropic.java`, `DiglineMessages.java` | `addInterceptor` on the client's builder, with the SDK's own interface, not OkHttp's |
| `software.amazon.awssdk:bedrockruntime` | `DiglineRecorder.java`, `DiglineAws.java`, `DiglineMessages.java` | an execution interceptor on the client's configuration |

**Which of Bedrock's calls are recorded.** `converse` and `converseStream`,
and `invokeModel` and `invokeModelWithResponseStream` with an Anthropic model,
whose body is Anthropic's Messages, read as a direct call to Anthropic is.
`invokeModel` with another family, Titan, Llama or Mistral, is not recorded,
and neither is an embedding model: each call is counted in
`recorder.counts()` with its reason, *model family not recorded* or
*embeddings not recorded*, and standard error says it once a family, as
`digline recorder: invoke_model on amazon.titan-text-express-v1: this model
family is not recorded`. The family is read from the model id, a cross-region
prefix (`us.`, `eu.`, `apac.`, `global.`) taken off first. This writer keeps
no counts file, so `digline record status` does not see those calls: standard
error and `recorder.counts()` are where they show.

The recorder is made once, for the application, with the directory that holds
`.digline/`, the tenant and the application's name, and each client takes the
hook:

```java
DiglineRecorder recorder = DiglineRecorder.development(root, "acme", "support");

OpenAIClient openai = OpenAIOkHttpClient.builder()
        .fromEnv()
        .addInterceptor(new DiglineOkHttp(recorder))
        .build();

AnthropicClient anthropic = AnthropicOkHttpClient.builder()
        .fromEnv()
        .addInterceptor(new DiglineAnthropic(recorder))
        .build();

BedrockRuntimeClient bedrock = BedrockRuntimeClient.builder()
        .overrideConfiguration(c -> c.addExecutionInterceptor(new DiglineAws(recorder)))
        .build();
```

A call names its suite, the same name as that suite's `Suite(name=...)`, for
as long as the scope is open on the thread that makes it. A call that names
none is recorded under `_unassigned`, with the class and method it was made
from:

```java
try (var suite = DiglineRecorder.suite("refunds")) {
    openai.chat().completions().create(params);
}
```

It records nothing until the tenant's switch says so, the file
[`digline record on`](record.md#switching-it-on) writes, which the writer reads
with digline's own rules and reads again at its interval. Without the file the
recorder is off, and so it is where the root holds no `.digline/`. In
development `DIGLINE_RECORD=1` switches it on where no file exists.

### A turn of an agent

An episode keeps one turn as one recording, with the calls made inside it as
its steps. It is written when the scope closes. Java's try-with-resources does
not tell the scope why it closed, so **a turn that ended by an exception says
so in its `catch`**, and the recording then says *interrupted*:

The episode names its own suite, and not its calls': each call names one, or
is recorded under `_unassigned`. So a scope inside the episode names the suite
of the calls the turn makes:

```java
try (var episode = recorder.episode("order-agent", Map.of("ticket", ticket));
        // The turn's calls name their suite here, or they are _unassigned.
        var calls = DiglineRecorder.suite("order-agent")) {
    try {
        String answer = agent.answer(ticket);
        episode.output(answer);
    } catch (RuntimeException failed) {
        episode.interrupted();
        throw failed;
    }
}
```

A call made on another thread belongs to the episode where that thread
attaches it, by the episode's id, which is `null` while the recorder is off:

```java
String id = episode.id();
pool.submit(() -> {
    try (var attached = DiglineRecorder.attach(id)) {
        return lookup(order);
    }
});
```

### In production

`production` takes a function asked at every call, and each tenant's
recordings are filed under its own directory. It refuses to start, with a
`StartError`, where a tenant's file is invalid, or switches recording on
without `redact`, `sample` and `ceiling`, as `digline record on --production`
writes them. It also refuses where `DIGLINE_RECORD=1` is set:

```java
DiglineRecorder recorder = DiglineRecorder.production(root, () -> tenantOf(request), "support");
```

`digline record on` speaks of *an application that names its tenant with a
function*, which is Python's way of saying production. In Java it is
`DiglineRecorder.production`.

An application with one tenant, deployed, uses
`production(root, () -> "acme", app)`, so the file must declare `redact`,
`sample` and `ceiling`.

### An asynchronous call

Neither SDK's asynchronous client calls the hook on the thread that made the
call: it calls it on a thread of its own, where no suite is named and no
episode attached. Such a call is recorded under `_unassigned`, outside the
episode the calling thread had open, as an orphan of it, and with no call
site. An `attach(id)` in the future's callback comes too late: the call has
been made, and recorded, before any callback runs.

A call that belongs to a suite or an episode is made with the synchronous
client, on a thread of your own that names them:

```java
String id = episode.id();
CompletableFuture<ChatCompletion> later = CompletableFuture.supplyAsync(() -> {
    try (var attached = DiglineRecorder.attach(id);
            var suite = DiglineRecorder.suite("refunds")) {
        return openai.chat().completions().create(params);
    }
}, pool);
```

### When a framework builds the client

In a Quarkus application that builds its Bedrock client with the SDK v2
builder, in a CDI bean or not, the hook goes on that builder, and a suite is
named around the call. A call that names no suite carries the class and method
it was made from; where every call goes through one method of the
application's, that is the same method for every call, so the suite is what
names it.

```java
BedrockRuntimeClient client = BedrockRuntimeClient.builder()
        .overrideConfiguration(c -> c.addExecutionInterceptor(new DiglineAws(recorder)))
        .build();
```

In a CDI bean, `root` comes from configuration, since the working directory
differs between tests, dev mode and a deployed jar.

And the one method every call goes through names the suite:

```java
<T> T ask(String feature, Supplier<T> call) {
    try (var suite = DiglineRecorder.suite(feature)) {
        return call.get();
    }
}
```

LangChain4j's Bedrock chat model takes such a client,
`BedrockChatModel.builder().client(client)`. The call site skips LangChain4j's
package as it skips the SDKs', so a call made through it is named by the first
frame outside both, not by LangChain4j's class. That was measured with a
stand-in class in LangChain4j's package, not with LangChain4j itself.

For new code on Bedrock, Converse is the form to prefer: one API for every
chat model, tool use in the same shape, and streaming as events. The two forms
record a different case and setup, so a suite whose calls mix them has two
setups, and only the newest one's answers can be written.

## With LangChain4j or Quarkus: the proxy

LangChain4j calls OpenAI through its own JDK `HttpClient`, and
Quarkus-LangChain4j through Quarkus's REST client: neither goes through an
SDK the hooks hook. For them the door is
[`digline record proxy`](record.md#through-the-proxy-digline-record-proxy),
and what changes is configuration:

- **LangChain4j**: `baseUrl("http://127.0.0.1:8787/v1")` on the model's
  builder, and `customHeaders(Map.of("X-Digline-Suite", "refunds"))` for the
  suite;
- **Quarkus-LangChain4j**, which sets no header from its configuration:
  `quarkus.langchain4j.openai.base-url=http://127.0.0.1:8787/suite/refunds/v1`,
  the suite in the path.

The proxy does what the files do, and its page says how: the same switch,
episodes by a header, a stream recorded at its end.

## Running the gate from a Java app

The gate is a suite, and digline calls a Java app the way it calls any app it
did not write: over HTTP, at an endpoint the app serves, with an
[`http` target](declarative.md#type-http). A `suite.toml` beside the app:

```toml
[suite]
tenant = "acme"
environment = "dev"
name = "refunds"
cases = ["cases.json", "captured.json"]
samples = 2
min_agreement = "2/2"

[capture]
cases_file = "captured.json"
repository = "private"
check = "llm_rubric"

[target]
type = "http"
url = "http://127.0.0.1:8080/answer"
output_path = "answer"
config_path = "config"
tool_calls_path = "trajectory.calls"
usage_path = "usage"

  [target.body]
  messages = "case.vars.messages"

[[assertions]]
type = "llm_rubric"
rubric = "Does the reply answer what the customer asked?"
judge = "openai/gpt-4o-mini"
threshold = 0.7
tolerance = 0.05
```

- **The body** sends the case's `messages`, which is what a case imported
  from a single call holds: the conversation the call was given, less the
  instructions. A case imported from an episode holds the `case` its turn was
  given instead, `ticket` in the episode above, and a body for it sends
  `case.vars.ticket` ([the recording document](recording-format.md)). The
  endpoint answers with the reply under `answer`; under `config` what model
  answered and how; under `trajectory.calls` the tools it called; under
  `usage` the token counts. Each of the last three is optional, and
  [the `http` target](declarative.md#type-http) says what leaving one out
  costs.
- **The judge** is a provider's model, by `provider/model`, through the
  plugin installed with the CLI. Its key is the application's, read from the
  environment where the run happens, `OPENAI_API_KEY` here: no key is ever
  written in a suite.
- **`[capture]`** names the file the import writes, the one `cases` loads
  beside `cases.json`, and the judged check the reviewed answers are for.
- **`cases.json` holds the cases of your own.** A suite that declares
  `[capture]` loads with no case yet, the import included, and
  `digline run` on it judges nothing and exits `2`, never a green.

A suite of reviewed answers alone never calls the target: each reviewed answer
is judged on the answer the application gave, and the run says so, *with no
call to the target*. Such a suite may leave `[target]` out. A case the target
answers, added to it later, is refused when the suite is loaded, and the
refusal names the case.

```console
$ digline record import --tenant acme --suite suite.toml
$ digline run --suite suite.toml
```

## Spring AI

Not measured: no version of Spring AI was read for this page. Whether its
client can be pointed at the proxy, and how, is not known here.

## What stays out

- **A call made through an asynchronous client** is recorded under
  `_unassigned`, as an orphan of the episode open on the calling thread: see
  [An asynchronous call](#an-asynchronous-call).
- **Another endpoint of the same SDK.** `DiglineOkHttp` reads Chat
  Completions and nothing else, so OpenAI's Responses API goes through
  unrecorded. `DiglineAnthropic` reads Messages. `DiglineAws` reads Converse
  and ConverseStream, and InvokeModel with an Anthropic model.
- **`extra_body`.** On the wire its keys are merged into the request. The
  OpenAI and Anthropic plugins' recorder maps merge it the same way from their
  next release (#919), and until then a call that sends `extra_body` has
  another setup digest in Python than here.
- **A stream not read to its end.** A stream is recorded when the application
  has read it to its end. One closed before is counted *stream abandoned*.
  OpenAI's SDK stops reading at `[DONE]`, and Anthropic's at `message_stop`:
  either counts as the end.
- **The counts.** The writer keeps no counts file, which is not part of the
  contract. `digline record status` says *not counted* for its process, and
  `recorder.counts()` gives the same counts in memory.
- **HTTP/2 to Bedrock.** `converseStream` was run over HTTP/1.1 against the
  fake provider, where Bedrock itself speaks HTTP/2. The hook sits above the
  transport and reads the same bytes, but that was not measured against AWS.
- **A switch file the reader does not know.** The writer reads the TOML a
  switch holds. An array, a date or a dotted key is refused, as digline's
  reader refuses it, but in another sentence.
- **Tests that build the client with the hook record too**, while the switch
  is on: point the root of the test profile at a directory with no
  `.digline/`, or switch it off.
