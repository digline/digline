# digline for Java

An application written in Java keeps the calls it makes to a model as
recordings, the files [`digline record`](record.md) turns into a suite's
cases. Which door it goes through depends on what makes the call:

| What makes the call | The door | How it was read |
|---|---|---|
| The official OpenAI Java SDK, the official Anthropic Java SDK, the AWS SDK v2 for Bedrock | **Two files copied into the project**, a writer and a hook for the client | run by `recorders/java`'s tests, on each SDK's real client against a fake provider on `127.0.0.1` |
| LangChain4j, Quarkus-LangChain4j | **[`digline record proxy`](record.md#through-the-proxy-digline-record-proxy)**, with the base URL from configuration and the suite in a header or the path | LangChain4j with a header, single and streamed, run through the proxy by the CI job `through-the-proxy` on every pull request; Quarkus-LangChain4j by the path alone, run through the proxy for [ADR 0062](adr/0062-the-recorder-out-of-process-and-in-other-processes.md) on 2026-11-04 |
| Spring AI | not measured | no version of it was read |

Either way the files are the same, and so is everything downstream:
`digline record import`, `compare`, the page, a run. What a file holds is
[the recording document](recording-format.md).

No call to a provider was made for this page: the SDKs were run against fake
providers that answer in each provider's shape.

## With an official SDK: two files

Copy `DiglineRecorder.java`, and the hook for your client, from
`recorders/java/src/main/java/dev/digline/` in digline's repository into your
project, in the package `dev.digline`. They need Java 21. The writer needs the
JDK alone, and each hook needs only the SDK it hooks:

| Your client | The hook | How it is installed |
|---|---|---|
| `com.openai:openai-java`, or any OkHttp client calling Chat Completions | `DiglineOkHttp.java` | `addInterceptor` on the client's builder |
| `com.anthropic:anthropic-java` | `DiglineAnthropic.java` | `addInterceptor` on the client's builder, with the SDK's own interface, not OkHttp's |
| `software.amazon.awssdk:bedrockruntime`, `converse` and `converseStream` | `DiglineAws.java` | an execution interceptor on the client's configuration |

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

```java
try (var episode = recorder.episode("order-agent", Map.of("ticket", ticket))) {
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

## Spring AI

Not measured: no version of Spring AI was read for this page. Whether its
client can be pointed at the proxy, and how, is not known here.

## What stays out

- **A call made through an asynchronous client.** A suite, an episode and
  an attached id are the calling thread's, and neither SDK's asynchronous
  client calls the hook on that thread. Measured on both: such a call is
  recorded under `_unassigned` and outside the episode the calling thread
  had open, as an orphan of it, whatever that thread named.
- **Another endpoint of the same SDK.** `DiglineOkHttp` reads Chat
  Completions and nothing else, so OpenAI's Responses API goes through
  unrecorded. `DiglineAnthropic` reads Messages, and `DiglineAws` reads
  Converse and ConverseStream.
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
