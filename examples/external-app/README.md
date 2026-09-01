# My application is Java: can I use this?

Yes, and nothing here is about Java. digline needs a body it can post and a
field it can read out of the answer; what produced the answer is not its
business. Your service can be a JVM app, a Go binary, a gateway, a shell script
behind `nc`.

`server.py` stands in for it — twenty lines of `http.server`, so the example
runs on its own. Point `URL` at your service, delete that file, and nothing
else in `suite.py` changes.

`HttpTarget` is the twenty lines every suite used to write by hand: a callable
that builds the body from the case, and dotted paths that say where the answer,
the cost and the elapsed time live in the response. Its `preflight` asks whether
anything is listening **before** the first case, so a service that is down fails
once with a sentence instead of five times with a stack trace.

`Equals` and not `Contains`: this endpoint answers with an object, and
`Contains` is text-only — digline refuses to stringify a dict and search inside
it, and says so.

```console
$ uv sync && uv run digline run --suite suite.py
```

If your service is a LangChain4j app and you would rather follow the whole
path — the endpoint, the three files, the report, the CI gate — go to
[`examples/langchain4j/`](../langchain4j/) instead. This one is the short
answer; that one is the walkthrough, and it also shows how the service reports
**which model answered**, which is what makes a model change visible in a
comparison.

Needs digline `0.1.2` (`HttpTarget`). No API key, no network beyond localhost.
