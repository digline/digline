# ADR 0062 — The recorder out of process, and in other processes

- Status: proposed 2026-11-04. **Its direction was ruled before this record
  was written**, by Alessandro Prandini on 2026-11-04, in the conversation of
  the session that wrote it: 1.1 serves the "before" to an application that is
  not written in Python, as widely as it can, and tells it language by
  language. Three doors, one format, and everything downstream of the format
  unchanged. **What this record adds is marked *decided here***: the names,
  the contract's fixed fields, the reading of a reply off the wire, and what
  the measurement below changed in the ruled shape. Each is proposed, for
  acceptance to take or remove item by item. Nothing in it is implemented
- Shipped: unreleased
- Date: 2026-11-04
- Opens: **nothing at this record's landing.** No `SCHEMA_VERSION`, no
  `OUTPUT_VERSION`, no line of `_STEPS`. `RECORDING_VERSION` stays 1: the
  format has not shipped, and §2 fixes it as it stands, with one key whose
  content it rules (`input`) and one it takes out of the contract (`label`)
- Amends, each by a dated note beside the place it amends, which points here.
  Every text is kept as written:
  - [ADR 0058](0058-the-recorder-a-call-recorded-where-the-application-makes-it.md)
    §10, *"The wrapper is Python. An application in another language is not
    served by it in 1.1"*, and its *Not decided here*, *"An application in
    another language"*, which this record decides for 1.1
- Assumes: [ADR 0058](0058-the-recorder-a-call-recorded-where-the-application-makes-it.md)
  §1 (tenant, app, suite), §3 (three compartments), §4 (where a recording
  lives, and the import that refuses another tenant), §5 (the episode), §8
  (the setup of an episode), §9 (a step, and who acted), §10 (the switch) and
  §11 (one serializer, and the recording's own version);
  [ADR 0059](0059-a-reviewed-answer-a-grouped-listing-a-source-as-data.md)
  (a reviewed answer needs the question it answers);
  [ADR 0060](0060-the-steps-of-a-trajectory-live-recorded-and-collected.md)
  (the steps); [ADR 0061](0061-a-local-page-whose-views-other-packages-may-extend.md)
  (the page reads the store)
- Touches: nothing in `CLAUDE.md`'s *fixed* section moves. **Decision 5 is
  upheld**: the proxy listens on `127.0.0.1` alone and calls only the
  provider the application was already calling, through the route the
  application chose; it adds no destination. **Decision 2 is upheld**: every
  door writes the same files into the same `.digline/<tenant>/recordings/`.
  **Decision 9 is upheld**: a recording is payload, written inside the
  perimeter, and nothing a door adds crosses a boundary
- Number: 0062. Swept on 2026-11-04, before a line was written, across
  `origin/main` (`790d6144`), whose highest record is 0061; every branch on the
  remote; every worktree of this repository; and the two open pull requests,
  #869 and #899, neither of which adds a record. The highest number taken
  anywhere is 0061
- Owed: the three lines on digline.dev that every new record needs (the nav,
  and the two tables the site builds its pages from). Until they land, the
  `docs` job reads red on this record's pull request, which is the state the
  site's runbook expects, and no required check reads it

**How to read the clauses.** *Ruled* is the direction taken before this
record. *Decided here* is a name or a detail this record proposes. *Measured*
is a figure read on this machine, on `main` at `43c2dcd1`, with prototypes
built outside the repository and not saved in it: the figures are indicative,
and the implementation owes the saved measurement, as ADR 0058 §10 owed its
own.

## Context

The recorder of ADR 0058 is a Python wrapper around the provider's own client,
inside the application. Its sentence on everything else is §10's: *"An
application in another language is not served by it in 1.1."* The ruling of
2026-11-04 turns that around, in Alessandro Prandini's words: *"we cannot tell
half a story; whoever builds enterprise software often does not use Python"*,
told language by language — *"if you build in Java, do this; in .NET, this"* —
and for no stack in particular.

What a recording becomes downstream is already built and does not change:
`digline record import` lists and writes reviewed answers (ADR 0059),
`digline record compare` shows answers by setup, the page reads the store
(ADR 0061), and a run judges the cases. All of it reads files. So the question
is only how a file gets written by a process that is not Python, and what the
file must hold to be read.

## What was measured

**Toolchains on this machine** (2026-11-04): Java 21.0.9 with Maven 3.9.9
and Gradle; Node 22.22.0. No .NET and no Go: what needs them below is **not
measured**, which is not the same as not working.

**The SDKs, and where a base URL and a header go**:

| SDK | Version read | Base URL | A header on every call | How it was read |
|---|---|---|---|---|
| OpenAI, Node | 7.50.0 | `OPENAI_BASE_URL`, or `baseURL` | `defaultHeaders` | run through the proxy, single and streamed |
| Anthropic, Node | 1.4.0 | `ANTHROPIC_BASE_URL`, or `baseURL` | `defaultHeaders` | run through the proxy, single and streamed |
| OpenAI, Java | 4.99.0 | `OPENAI_BASE_URL` (`fromEnv()`), or `baseUrl` | `putHeader` | its builder's signatures, read with `javap`; not run |
| Anthropic, Java | 3.4.0 | `ANTHROPIC_BASE_URL` (`fromEnv()`), or `baseUrl` | `putHeader`; the jar also names `ANTHROPIC_CUSTOM_HEADERS` | the same; not run |
| LangChain4j OpenAI | 1.22.0 | `baseUrl` | `customHeaders` | run through the proxy |
| Quarkus-LangChain4j OpenAI | 1.14.2 | `quarkus.langchain4j.openai.base-url` | **none in its configuration** | the repository's `examples/langchain4j/app-quarkus`, run through the proxy by configuration alone, the suite in the path |
| AWS SDK v2, Bedrock runtime | 2.42.41 | `endpointOverride` | an `ExecutionInterceptor` | run, with the interceptor below |
| OpenAI, .NET | not installed | `OpenAIClientOptions.Endpoint` | an `HttpClient` through `HttpClientPipelineTransport` | its README; not measured |
| Anthropic, .NET | not installed | not found in the README | not found in the README | not measured |
| OpenAI, Go | not installed | `OPENAI_BASE_URL`, `option.WithBaseURL` | `option.WithHeader`, `option.WithMiddleware` | its README; not measured |
| Anthropic, Go | not installed | `ANTHROPIC_BASE_URL`, `option.WithBaseURL` | `option.WithHeader`, `option.WithHTTPClient` | its README; not measured |

Spring AI was not read: no version of it was on this machine, and none was
fetched.

**The proxy**, a prototype on the standard library's `ThreadingHTTPServer`
and `http.client`, writing with digline's own `RecordingWriter` and reading
with the plugins' own maps, against a fake upstream on `127.0.0.1`. Over 300
alternating calls each, the median added by the proxy:

| | direct | through the proxy | added |
|---|---|---|---|
| a single reply | 0.18 ms | 0.33 ms | 0.15 ms |
| a stream of 50 events, to its first byte | 1.21 ms | 1.90 ms | 0.68 ms |
| the same stream, to its end | 140.03 ms | 140.58 ms | 0.56 ms |

A forward-only proxy, which records nothing, added 0.14 ms, 0.80 ms and
0.64 ms: the recording is written after the reply has been passed on, and
costs the caller nothing it can see. 600 recordings were written in the run,
and `digline record compare` and `digline record import` read all of them; an
answer from them was written as a reviewed answer with `--by`.

**Reading a reply off the wire.** Each plugin's recording map reads a request
that is the SDK call's keyword arguments, which are the JSON body field for
field, and a reply that is the SDK's object. Turning the JSON into the SDK's
own type (`ChatCompletion.model_validate` for OpenAI, `construct_type` for
Anthropic's `Message` and stream events) and handing it to the map gave the
same text, finish and usage for a single reply and for a stream, for both; a
Bedrock `converse` reply is a `dict` already, and its map read it as it is. The
SDKs are imported **before the server takes a request**: imported for the
first time by two handler threads at once, `anthropic.lib.streaming` failed
with a circular import, and those recordings were lost.

**Bedrock.** The proxy drops the application's signature and signs the same
body with the credentials of the machine it runs on, through botocore's
`SigV4Auth`, which the Bedrock plugin already carries. Against the fake
upstream the signature arrived as `AWS4-HMAC-SHA256` with the proxy's key, and
signing took 0.031 ms at the median of 200. A call to AWS was not made, and
`converse-stream`, whose reply is AWS's binary event stream, was not measured.

**The interceptor, in Java.** Three files compiled with `javac` 21 against the
libraries above: a writer with no dependency beyond the JDK, an OkHttp
`Interceptor`, and an AWS `ExecutionInterceptor`. The OkHttp one recorded a
call to the fake Anthropic route, and the AWS one recorded a Bedrock
`converse`, reading the body before the SDK unmarshals it. **The file the writer
left was read by `digline record import`**, listed, and electable: the
contract holds across a process and a language. The setup digest Java
computed for `{"max_tokens": 64, "model": "claude-haiku-4-5"}` was
`81869b20f0d8875a`, the one Python computes.

**What the measurement changed in the ruled shape:**

- **One file cannot hook every Java client.** A file that imports OkHttp does
  not compile in a project without it, and the AWS SDK is the same. So the
  writer is one file, and each hook is a file of its own (§4).
- **The official Anthropic Java SDK takes no OkHttp interceptor.** Its builder
  has `addInterceptor(com.anthropic.core.http.Interceptor)`, an interface of
  its own; OpenAI's has `addInterceptor(okhttp3.Interceptor)`. So the hooks are
  three, not two.
- **LangChain4j and Quarkus do not use OkHttp.** LangChain4j's OpenAI model
  goes through its JDK `HttpClient`, and Quarkus-LangChain4j through Quarkus's
  REST client. For a framework the door is the proxy, and its configuration
  is the base URL.
- **The in-process recorder writes no `input`.** `_record` and the episode's
  writer build the response without it, and ADR 0059's import refuses an
  answer without its question. So no answer recorded in process can be
  written as a reviewed answer today. §2 rules `input`, and the in-process
  recorder owes it (§2, *What the contract costs*).

## Decision

### 1. Three doors, one format — ruled

| Door | For | Where the call is recorded |
|---|---|---|
| **In process, Python** | a Python application | `digline.recorder.wrap`, around the client, as ADR 0058 has it |
| **The proxy** | any application whose SDK takes a base URL | `digline record proxy`, on `127.0.0.1`, between the SDK and the provider |
| **An interceptor, per language** | an application that wants the call recorded inside its own process | a file copied into the project, under the HTTP client |

**Each writes the same recording** into the same directory, and everything
downstream reads it without knowing which door wrote it: the listing, the
import, `compare`, the page, and the bench that will measure the judge. **No
door is a model client of digline's**: the call is the application's, made
through its SDK or its framework, and a door sits under it, in the HTTP (ADR
0058, *"recorded where the application makes it"*).

### 2. The format is a public contract — ruled, with its fields *decided here*

**`RECORDING_VERSION` is the contract's version**, already written in every
document, and a reader refuses another by name (ADR 0058 §11). A page of the
documentation states the contract (§5), and a writer in any language is held
to it.

**Fixed, as a writer must write them:**

- **The place**: `.digline/<tenant>/recordings/<process>/<n>.json`. `<process>`
  is a directory of the writer's own, unique to one process: digline's writes
  `p<pid>-<8 hex>`, and another writer chooses its own prefix. `<n>` counts from
  1, six digits. A file is written whole and moved or linked into place, so a
  reader never sees half of one. A name starting with `.` is the writer's own
  and is not read.
- **The top level**: `recording_version`, `source_tenant`, `app`, `suite`
  (`_unassigned` where none was named), `case`, `setup`, `setup_digest`,
  `response`, and, where they apply, `episode`, `id`, `steps`, `interrupted`,
  `unrecorded_children`, `orphan`, `call_site`, `recorded_at`.
- **`case` and `setup`** are JSON objects. `case` holds `messages`, the
  conversation the call was given, and what the import makes the case's
  `vars`. `setup` is everything else that decided how the call answered.
- **`setup_digest`** is the first 16 hexadecimal characters of the SHA-256 of
  `setup` written as Python's `json.dumps` writes it with sorted keys,
  separators `","` and `":"`, non-ASCII escaped as `\uXXXX`, and no NaN.
  Measured equal across Java and Python on strings and integers. **A float is
  where two languages write different text**, so *decided here*: a writer that
  cannot write a float as Python's `repr` does keeps the float out of its
  setup's digest by writing it as a string, and says so in its own page.
- **`recorded_at`** is ISO 8601 in UTC, written with `+00:00`. *Decided here*,
  because the import compares these as text today (`_setup_in_force`,
  `examined_through`): one form is what makes text order the time order, and
  a Java writer measured here wrote `Z`.
- **`response`** is the run document's recorded response: `output`, `kind`
  (`text`, `structured` or `conversation`), `input`, `latency_ms`, `usage`
  (`input_tokens`, `output_tokens`, and the cache and thinking counts where
  reported), `tool_calls`, and `withheld` or `oversize` where they apply.
- **`input`, *decided here*: the JSON text of the call's `messages`**, as the
  provider received them. It is the question a judge reads beside the answer,
  and ADR 0059's import refuses an answer without it.
- **A step**: `index` from 0 in order, `actor` `model` or `tool`, a model
  step's `finish` where one was reported, and a tool step's call in the run
  document's own keys (ADR 0058 §9, ADR 0060).

**Free**: what a writer puts inside `setup`, beyond its being JSON; the
`app` name; the name of its process directory. **Out of the contract, *decided
here***: the `label` compartment. ADR 0059 ruled that the import no longer
reads it, and a field no reader reads is not one a writer in another language
should be asked to fill. It stays readable, and the in-process recorder writes
none.

**What the contract costs**, and is owed with it:

- the in-process recorder starts writing `input`, single calls and episodes;
- the import compares `recorded_at` as an instant, or the contract's single
  form is enforced on read, refusing another by name;
- the `.counts` file a process keeps, read by `digline record status`, is not
  part of the contract: a writer outside Python leaves none, and the status
  says *not counted* for its process rather than *nothing recorded*.

### 3. The proxy — *decided here*

**The command**: `digline record proxy --tenant T [--port N]`, listening on
`127.0.0.1` alone. It reads the tenant's switch, `recorder.toml`, as the
in-process recorder does, with its sample and its ceiling: off, it forwards
and records nothing.

**Where it forwards**: by route, to the provider the route belongs to.
`/v1/chat/completions` and `/v1/responses` go to OpenAI, `/v1/messages` to
Anthropic, and `/model/<id>/converse` to Bedrock in the region the machine's
AWS configuration names. `--upstream ROUTE=URL` changes one, for a gateway or
a compatible endpoint. The application's own key travels as it was sent, and
the proxy holds none for OpenAI or Anthropic.

**The suite, the app and the episode**, three ways, the first that is given:

- headers: **`X-Digline-Suite`**, **`X-Digline-App`**, **`X-Digline-Episode`**
  (an id the application chooses, as `attach(id)` takes one);
- the path: **`/suite/<name>/`** before the provider's path, for an application
  that can set a base URL and no header. Quarkus-LangChain4j is one, measured;
- neither: the suite is `_unassigned`, as ADR 0058 §2 has it for a call that
  names none, and the app is `proxy`.

The `X-Digline-*` headers and the path prefix are taken off before the call
goes on: measured, the provider receives neither.

**Streaming** is passed on as it arrives and read when it ends, from the bytes
that were passed on: the caller waits for nothing the proxy does.

**Reading a call off the wire**: a new entry point, **`digline.recording_wire`**,
in the plugins, one entry per route. An entry turns the request's JSON and the
reply's JSON, or each streamed event, into the SDK's own types, and hands them
to the plugin's recording map. The map is unchanged, and it is shared with the
in-process recorder and with the target's `completion_of`: a call reads the
same through every door. The Bedrock entry lives in the Bedrock plugin. Every
entry is loaded when the proxy starts, never at the first request.

**Bedrock**: the proxy does not rewrite the application's signature. It signs
the call again with the machine's own AWS credentials, through botocore, and
calls Bedrock itself, as a gateway does; the application points its SDK at
the proxy with `endpointOverride` and any credentials.

**An agent's steps**, through the proxy, are rebuilt from the conversation:
the tool call in one reply and its `tool_result` in the next request, joined
by the episode's header. Not measured.

**What it does not see**: a call the application does not point at it; a
call over a route it does not know, which it forwards and does not record;
and the application's own code between two calls, so an episode's steps are
what crossed the wire.

### 4. The interceptor, per language — *decided here*, Java in 1.1

**A writer and a hook, each a file copied into the project.** Not a library
on Maven Central until somebody asks for one.

- **`DiglineRecorder.java`**: the writer, JDK only. It writes the contract's
  file, with `RECORDING_VERSION` in it, and holds the suite and the episode of
  the calls made on a thread (`DiglineRecorder.suite(...)`,
  `DiglineRecorder.episode(...)`, each a `ThreadLocal`).
- **`DiglineOkHttp.java`**: an `okhttp3.Interceptor`, for the official OpenAI
  Java SDK (`addInterceptor`) and any OkHttp client.
- **`DiglineAnthropic.java`**: a `com.anthropic.core.http.Interceptor`, for the
  official Anthropic Java SDK, whose builder takes no OkHttp interceptor. Not
  measured.
- **`DiglineAws.java`**: an AWS SDK v2 `ExecutionInterceptor`, for Bedrock's
  `converse`. Measured; `converse-stream` is not.

A hook never fails the call: a reading that fails leaves the call unrecorded
and the application's reply as it was.

**A façade for an application with no framework**: **`Digline.ask(suite,
prompt)`**, about twenty lines over the hook, which names the suite and calls
the client the application built. Never a client of digline's own: Spring AI
and LangChain4j own the call, and digline stays under it, in the HTTP, where
for those two the proxy is the door (§1, *What was measured*).

**One CI job per language**, `recorder-java` in 1.1: it compiles the files
against the libraries they hook, runs a call to a fake upstream through each,
and has `digline record import` read what was written. That is the contract
held where it is written, and the job is required where the files ship.

**.NET** (a `DelegatingHandler`), **Node** (around `fetch`) and **Go** (an
`http.RoundTripper`) come after 1.1, each with its own job.

### 5. A page per language — *decided here*

**`docs/record-java.md`, and then `record-dotnet.md`, `record-node.md` and
`record-go.md`**: what a developer in that language does, in three lines that
were run with a minimal project — the base URL, the suite's header or path,
the episode — and then the interceptor where there is one, and what stays out.
**A line goes on a page only once it was run**: a page says *not measured*
where it was not, as the table above does. **`docs/recording-format.md`**
states the contract of §2.

### 6. OpenTelemetry is not the "before" — ruled

The generative-AI conventions do not carry the text of a prompt or a reply
without an opt-in of their own, and a recording is the text. OpenTelemetry
stays for the "after", the production side, which this record does not open.

### 7. The order of the work, and its cost — *decided here*

1. the contract's costs (§2): `input` in the in-process recorder, and
   `recorded_at` read as an instant: **1 day**;
2. the proxy, with `digline.recording_wire` in the three plugins, OpenAI and
   Anthropic single and streamed, Bedrock `converse`: **4 days**. Bedrock's
   `converse-stream` and an agent's steps rebuilt from messages: **2 days
   more**, measured first;
3. the Java files, their CI job, and `docs/record-java.md` with a Quarkus
   project as its proof: **3 days**;
4. `docs/recording-format.md`, and pages for Node, .NET and Go saying what the
   proxy does for them and what is not measured: **2 days**.

About **12 days** for 1.1. The interceptors for .NET, Node and Go are after.

## What does not change

- **A recording's place, its compartments and its version** (ADR 0058 §3, §4,
  §11), now written by more than one writer.
- **The import, `compare`, the page and the run** read files, and do not know
  which door wrote them.
- **The import refuses another tenant's recordings** (ADR 0058 §4): a proxy is
  started for one tenant, and writes that tenant's.
- **The switch decides** whether anything is recorded (ADR 0058 §10), for the
  proxy as for the wrapper. An interceptor reads the same file.
- **Nothing leaves the machine that was not already leaving it.**

## Consequences

**An application in Java, Node, .NET or Go gets the "before"** through the
proxy, with a base URL and, where it can, a header, and an application in
Java can record inside its own process too. **The recording becomes a format
other people write**, so a change to it is a change to a contract, and a
field is added the way an `OUTPUT_VERSION` key is: additive, or a new version.

**The in-process recorder is corrected by this record's first item**: without
`input`, no answer it records can become a reviewed answer.

## Not decided here

- **The interceptors for .NET, Node and Go**, and their pages beyond what the
  proxy does.
- **OpenTelemetry**, for the "after".
- **The bridge** (ADR 0058, *Not decided here*): §3's proxy records one
  tenant, and bringing it to another is still the bridge.
- **A float in a setup's digest across languages**, beyond §2's rule of
  writing it as a string.
- **Whether a proxy may serve more than one tenant**, by a header: it may not
  in this record.
