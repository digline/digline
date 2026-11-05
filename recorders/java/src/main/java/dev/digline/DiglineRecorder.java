/*
 * digline's recorder for Java: the writer.
 *
 * RECORDING_VERSION 1, written to the contract as it stood on 2026-11-05:
 * https://github.com/digline/digline/blob/main/docs/recording-format.md
 *
 * Copy this file into your project, under the package dev.digline. It needs
 * the JDK alone, version 21 or later. A hook beside it reads your HTTP
 * client's calls and hands them here: DiglineOkHttp.java, DiglineAnthropic.java
 * or DiglineAws.java. digline's repository holds the copy its tests run, in
 * recorders/java/, and a change to the format is a new RECORDING_VERSION there.
 *
 * Licensed as digline is: Apache-2.0.
 */
package dev.digline;

import java.io.IOException;
import java.io.InputStream;
import java.math.BigDecimal;
import java.math.BigInteger;
import java.math.MathContext;
import java.math.RoundingMode;
import java.nio.charset.StandardCharsets;
import java.nio.file.DirectoryStream;
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.attribute.BasicFileAttributes;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ThreadLocalRandom;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.ReentrantLock;
import java.util.function.Supplier;

/**
 * Records the calls an application makes to a model, as files digline reads:
 * {@code .digline/<tenant>/recordings/j<pid>-<8 hex>/000001.json} and on. What
 * becomes of them is digline's: {@code digline record import} lists them and
 * writes the answers a person reviews into a suite's cases.
 *
 * <pre>{@code
 * DiglineRecorder recorder = DiglineRecorder.development(root, "acme", "support");
 * try (var suite = DiglineRecorder.suite("refunds")) {
 *     client.chat().completions().create(params);    // through a hook
 * }
 * }</pre>
 *
 * <p><b>The switch is the tenant's {@code recorder.toml}</b>, the file
 * {@code digline record on} writes, read with the rules digline's own recorder
 * reads it with: {@code on}, {@code sample}, {@code redact}, {@code ceiling},
 * {@code interval} and {@code production}, and any other key refused by name.
 * It is read again every {@code interval} seconds, without a restart. Without
 * a file the recorder is off, a root with no {@code .digline/} included,
 * unless {@code DIGLINE_RECORD=1} in development.
 *
 * <p><b>Two regimes.</b> {@link #development} takes the tenant's name: a
 * switch file that is invalid is said once on standard error and leaves the
 * recorder off. {@link #production} takes a function asked at every call, and
 * refuses to start, with a {@link StartError}, where a tenant's file is invalid
 * or switches recording on without {@code redact}, {@code sample} and
 * {@code ceiling}, or where {@code DIGLINE_RECORD=1}.
 *
 * <p><b>The application's call never fails because of the recorder.</b>
 * {@link #record} never throws: what goes wrong is counted, by reason, in
 * {@link #counts}. Unlike digline's own recorder, this one keeps no
 * {@code .counts} file, which is not part of the contract, so
 * {@code digline record status} says <i>not counted</i> for its process.
 *
 * <p><b>Suites and episodes are named per thread</b>, with {@link #suite},
 * {@link #episode} and {@link #attach}, each closed by try-with-resources,
 * which puts back what the thread had before.
 */
public final class DiglineRecorder {

    /** The recording's format version: the contract this file writes. */
    public static final int RECORDING_VERSION = 1;

    /** The suite of a call that names none. It enters no gate until a person assigns it. */
    public static final String UNASSIGNED = "_unassigned";

    /** The variable that switches recording on in development, where no switch file exists. */
    public static final String ENVIRONMENT_VARIABLE = "DIGLINE_RECORD";

    /** The keys a switch file may hold, and nothing else. */
    public static final List<String> SWITCH_KEYS =
            List.of("on", "sample", "redact", "ceiling", "interval", "production");

    static final double DEFAULT_SAMPLE = 1.0;
    static final long DEFAULT_CEILING = 100L * 1024 * 1024;
    static final double DEFAULT_INTERVAL = 5.0;

    /** The ceiling for one recorded field, in characters: over it, whole or nothing. */
    static final int MAX_RECORDED_CHARS = 65_536;

    /** Floats a recorded number is kept to, as digline's documents keep them. */
    static final int FLOAT_PRECISION = 6;

    /** What digline writes into {@code .digline/} when it lays a tenant out. */
    static final String GITIGNORE = "# Generated by digline. Run artifacts are ephemeral;\n"
            + "# baselines under <tenant>/baselines/ are meant to be committed.\n"
            + "*/runs/\n"
            + "# The name table is the re-identification key, and never committed.\n"
            + "*/name-table/\n"
            + "# Recordings are payload, and a committed switch would turn recording on\n"
            + "# for whoever clones the repository. (ADR 0058)\n"
            + "*/recordings/\n"
            + "*/recorder.toml\n";

    static final String GITATTRIBUTES =
            "# Generated by digline. The register is append-only, so two branches that\n"
            + "# each added a line keep both when they merge.\n"
            + "*/register/*.jsonl merge=union\n";

    private static final String STORE = ".digline";
    private static final String SWITCH_FILE = "recorder.toml";
    private static final String RECORDINGS = "recordings";
    private static final String CEILING_MARKER = "ceiling-reached.json";
    private static final int CLOSED_KEPT = 10_000;

    /** Raised when a recorder cannot start: never by a call. */
    public static final class StartError extends RuntimeException {
        private static final long serialVersionUID = 1L;

        public StartError(String message) {
            super(message);
        }
    }

    // ---------------------------------------------------------------- per thread

    private static final ThreadLocal<String> SUITE = new ThreadLocal<>();
    private static final ThreadLocal<String> CURRENT = new ThreadLocal<>();

    /** The episodes open in this process, by id. */
    private static final Map<String, Collector> OPEN = new ConcurrentHashMap<>();

    /** The episodes this process closed, most recent last, bounded. */
    private static final Map<String, Boolean> CLOSED = Collections.synchronizedMap(
            new LinkedHashMap<String, Boolean>() {
                private static final long serialVersionUID = 1L;

                @Override
                protected boolean removeEldestEntry(Map.Entry<String, Boolean> eldest) {
                    return size() > CLOSED_KEPT;
                }
            });

    /** One writer per root in this process, so the process has one directory per tenant. */
    private static final Map<Path, Writer> WRITERS = new ConcurrentHashMap<>();

    /** What a scope puts back when it closes. */
    public interface Scope extends AutoCloseable {
        @Override
        void close();
    }

    /**
     * Names the suite of the calls this thread makes until it closes: the same
     * name as that suite's {@code Suite(name=...)}. {@code null} names none.
     */
    public static Scope suite(String name) {
        String before = SUITE.get();
        SUITE.set(name == null || name.isEmpty() ? null : name);
        return () -> restore(SUITE, before);
    }

    /**
     * Puts the calls this thread makes, until it closes, in the episode
     * {@code id}: for a thread the episode was not opened on. {@code null},
     * which is an episode's id while the recorder is off, attaches nothing.
     */
    public static Scope attach(String id) {
        if (id == null || id.isEmpty()) {
            return () -> { };
        }
        String before = CURRENT.get();
        CURRENT.set(id);
        return () -> restore(CURRENT, before);
    }

    private static void restore(ThreadLocal<String> local, String before) {
        if (before == null) {
            local.remove();
        } else {
            local.set(before);
        }
    }

    // ---------------------------------------------------------------- the recorder

    private final Path root;
    private final String app;
    private final String tenant;
    private final Supplier<String> tenantFunction;
    private final boolean production;
    private final Writer writer;

    private volatile Map<String, Switch> switches = Map.of();
    private volatile boolean anyOn;
    private volatile Map<String, Stamp> stamps = Map.of();
    private volatile double interval = DEFAULT_INTERVAL;
    private volatile long nextLook;
    private final ReentrantLock lookLock = new ReentrantLock();
    private final Map<String, Long> sizes = new ConcurrentHashMap<>();
    private final Set<String> stopped = ConcurrentHashMap.newKeySet();
    private volatile String[] commit;

    private final Object countLock = new Object();
    private long recorded;
    private long orphans;
    private final Map<String, Long> notRecorded = new TreeMap<>();
    private final Map<String, Long> noted = new TreeMap<>();

    private DiglineRecorder(Path root, String app, String tenant, Supplier<String> tenantFunction) {
        if (app == null || app.isEmpty()) {
            throw new StartError("DiglineRecorder needs app, a non-empty name");
        }
        this.root = root;
        this.app = app;
        this.tenant = tenant;
        this.tenantFunction = tenantFunction;
        this.production = tenantFunction != null;
        this.writer = WRITERS.computeIfAbsent(
                root.toAbsolutePath().normalize(), key -> new Writer(root));
        boolean environment = switchedOn();
        if (production && environment) {
            throw new StartError(ENVIRONMENT_VARIABLE + "=1 with a tenant function, which is "
                    + "production: the variable declares no redaction and no sampling, so in "
                    + "production recording is switched on per tenant by its file (digline "
                    + "record on --production) (ADR 0058 §10)");
        }
        readSwitches(true);
        measure();
        nextLook = System.nanoTime() + nanos(interval);
    }

    /**
     * Development: one tenant, by name. {@code root} is the directory that
     * holds {@code .digline/}, usually the repository's root.
     */
    public static DiglineRecorder development(Path root, String tenant, String app) {
        if (tenant == null || tenant.isEmpty()) {
            throw new StartError("DiglineRecorder needs tenant, a non-empty name");
        }
        return new DiglineRecorder(Objects.requireNonNull(root, "root"), app, tenant, null);
    }

    /**
     * Production: the tenant is the function's answer at every call, and each
     * tenant's recordings are filed under its own directory.
     */
    public static DiglineRecorder production(Path root, Supplier<String> tenant, String app) {
        return new DiglineRecorder(Objects.requireNonNull(root, "root"), app, null,
                Objects.requireNonNull(tenant, "tenant"));
    }

    /** One call, as a hook read it. */
    public record Call(
            Map<String, Object> caseCompartment,
            Map<String, Object> setup,
            String output,
            double latencyMs,
            Usage usage,
            String finish,
            List<ToolCall> toolCalls) {
    }

    /**
     * What one call consumed. The two cache counts are 0 where none was
     * reported; {@code thinkingTokens} is {@code null} where none was.
     */
    public record Usage(long inputTokens, long outputTokens, long cacheReadTokens,
            long cacheWriteTokens, Long thinkingTokens) {

        public Usage(long inputTokens, long outputTokens) {
            this(inputTokens, outputTokens, 0, 0, null);
        }

        Map<String, Object> asMap() {
            Map<String, Object> found = new TreeMap<>();
            found.put("input_tokens", inputTokens);
            found.put("output_tokens", outputTokens);
            if (cacheReadTokens != 0) {
                found.put("cache_read_tokens", cacheReadTokens);
            }
            if (cacheWriteTokens != 0) {
                found.put("cache_write_tokens", cacheWriteTokens);
            }
            if (thinkingTokens != null) {
                found.put("thinking_tokens", thinkingTokens);
            }
            return found;
        }
    }

    /**
     * One tool call the model asked for. {@code tool} is {@code null} where
     * the provider named none; {@code arguments} is a map, a string, or
     * {@code null}. A client-side call is {@code status = "not_reported"} with
     * {@code resultAbsence = "not_reported"}: the reply ends where the tool
     * would start.
     */
    public record ToolCall(String tool, Object arguments, String status, String result,
            String resultAbsence) {

        public static ToolCall asked(String tool, Object arguments) {
            return new ToolCall(tool, arguments, "not_reported", null, "not_reported");
        }

        Map<String, Object> asMap() {
            Map<String, Object> found = new TreeMap<>();
            if (tool == null) {
                found.put("tool_absence", "not_reported");
            } else {
                if (tool.isEmpty()) {
                    throw new IllegalArgumentException("a tool call names a tool, or null");
                }
                found.put("tool", tool);
            }
            if (arguments != null) {
                found.put("arguments", arguments instanceof String text
                        ? text : Json.compact(rounded(arguments)));
            }
            if (result != null) {
                found.put("result", result);
            }
            if (resultAbsence != null) {
                found.put("result_absence", resultAbsence);
            }
            if (!"success".equals(status)) {
                found.put("status", status);
            }
            return found;
        }
    }

    /**
     * Whether any tenant records, as of the last look: what a hook asks before
     * it reads a request, so that an off recorder costs one test.
     */
    public boolean on() {
        lookIfDue();
        return anyOn;
    }

    /** Records one call, or counts why not. Never throws. */
    public void record(Call call) {
        try {
            lookIfDue();
            if (!anyOn) {
                return;
            }
            String suite = SUITE.get();
            String inside = CURRENT.get();
            String site = suite == null ? callSite() : null;
            boolean late = inside != null && !OPEN.containsKey(inside) && CLOSED.containsKey(inside);
            String[] outcome = recordCall(call, suite, inside, site, late);
            String reason = outcome[0];
            if (reason == null && late) {
                note("ended after its episode");
            }
            Seen seen = reason == null || "writer".equals(reason) ? seenOf(call) : null;
            joined(late ? null : inside, reason, seen);
        } catch (RuntimeException | Error unexpected) {
            count("unexpected: " + unexpected.getClass().getSimpleName());
        }
    }

    /**
     * Counts a call a hook could not read, by the stage that failed: what
     * digline's recorder counts as {@code map}, or {@code streaming}.
     */
    void miss(String reason) {
        try {
            lookIfDue();
            if (anyOn) {
                String inside = CURRENT.get();
                boolean late = inside != null && !OPEN.containsKey(inside) && CLOSED.containsKey(inside);
                joined(late ? null : inside, reason, null);
            }
        } catch (RuntimeException unexpected) {
            count("unexpected: " + unexpected.getClass().getSimpleName());
        }
    }

    /**
     * {@code recorded}, {@code not_recorded} by reason, {@code orphan} and
     * {@code noted}, as of now, in memory, as digline's {@code digline_counts}.
     */
    public Map<String, Object> counts() {
        synchronized (countLock) {
            Map<String, Object> found = new TreeMap<>();
            found.put("recorded", recorded);
            found.put("not_recorded", new TreeMap<>(notRecorded));
            found.put("orphan", orphans);
            found.put("noted", new TreeMap<>(noted));
            return found;
        }
    }

    private void count(String reason) {
        synchronized (countLock) {
            if (reason == null) {
                recorded++;
            } else {
                notRecorded.merge(reason, 1L, Long::sum);
            }
        }
    }

    private void note(String what) {
        synchronized (countLock) {
            noted.merge(what, 1L, Long::sum);
        }
    }

    private void joined(String inside, String reason, Seen seen) {
        count(reason);
        if (inside == null) {
            if (reason == null && !OPEN.isEmpty()) {
                synchronized (countLock) {
                    orphans++;
                }
            }
            return;
        }
        Collector collector = OPEN.get(inside);
        if (collector != null) {
            collector.add(seen);
        }
    }

    /** What a call adds to its episode, or {@code null} where it cannot be read. */
    private static Seen seenOf(Call call) {
        try {
            return new Seen(setupDigest(call.setup()), call.output(), call.finish(),
                    call.toolCalls() == null ? null : List.copyOf(call.toolCalls()));
        } catch (RuntimeException notJson) {
            return null;
        }
    }

    /** The reason a call was not recorded, or {@code null} where it was; never throws. */
    private String[] recordCall(Call call, String suite, String inside, String site, boolean late) {
        String stage = "tenant";
        try {
            String tenantNow = tenantNow();
            if (tenantNow == null) {
                return new String[] {stage};
            }
            Switch on = switches.get(tenantNow);
            if (on == null || !on.on) {
                return new String[] {"off for this tenant"};
            }
            Collector collector = inside == null ? null : OPEN.get(inside);
            if (collector != null) {
                if (collector.sampledOut) {
                    return new String[] {"sampled out"};
                }
            } else if (!sampledIn(on)) {
                return new String[] {"sampled out"};
            }
            if (atCeiling(tenantNow, on)) {
                return new String[] {"ceiling"};
            }
            stage = "map";
            if (call.caseCompartment() == null || call.setup() == null || call.output() == null) {
                return new String[] {stage};
            }
            stage = "not JSON";
            Map<String, Object> document = singleDocument(tenantNow, app, suite, call, now());
            if (inside != null) {
                document.put("episode", inside);
            }
            if (site != null) {
                document.put("call_site", site);
            }
            if (late || (inside == null && !OPEN.isEmpty())) {
                document.put("orphan", true);
            }
            stage = "writer";
            write(tenantNow, document);
        } catch (IOException | RuntimeException failed) {
            return new String[] {stage};
        }
        if (call.usage() == null) {
            note("usage not reported");
        }
        return new String[] {null};
    }

    /**
     * A single call's recording, before what only the moment of writing
     * knows: its episode, its call site, whether it is an orphan.
     */
    static Map<String, Object> singleDocument(String tenant, String app, String suite, Call call,
            String recordedAt) {
        Map<String, Object> caseCompartment = compartment(call.caseCompartment());
        Map<String, Object> setup = compartment(call.setup());
        return document(tenant, app, suite, caseCompartment, setup, setupDigest(setup),
                singleResponse(call, caseCompartment), recordedAt);
    }

    /** A single call's response, as {@code recorded()} builds it in digline. */
    static Map<String, Object> singleResponse(Call call, Map<String, Object> caseCompartment) {
        Object messages = caseCompartment.get("messages");
        String question = messages == null ? null : Json.compact(messages);
        List<Map<String, Object>> calls = null;
        List<Object> tools = null;
        List<Map<String, Object>> steps = null;
        if (call.toolCalls() != null) {
            calls = new ArrayList<>();
            tools = new ArrayList<>();
            for (ToolCall each : call.toolCalls()) {
                calls.add(each.asMap());
                tools.add(each.tool());
            }
            steps = stepsOf(List.of(new Step(call.finish(), call.toolCalls())));
        }
        long trajectory = 0;
        for (Map<String, Object> each : calls == null ? List.<Map<String, Object>>of() : calls) {
            trajectory += chars(each.get("tool")) + chars(each.get("arguments"))
                    + chars(each.get("result"));
        }
        for (Object name : tools == null ? List.of() : tools) {
            trajectory += chars(name);
        }
        Map<String, Object> response = new TreeMap<>();
        if (chars(call.output()) > MAX_RECORDED_CHARS || chars(question) > MAX_RECORDED_CHARS
                || trajectory > MAX_RECORDED_CHARS) {
            response.put("oversize", true);
            response.put("latency_ms", round(call.latencyMs()));
            if (call.usage() != null) {
                response.put("usage", call.usage().asMap());
            }
            return response;
        }
        response.put("output", call.output());
        response.put("kind", "text");
        if (question != null) {
            response.put("input", question);
        }
        response.put("latency_ms", round(call.latencyMs()));
        if (call.usage() != null) {
            response.put("usage", call.usage().asMap());
        }
        if (calls != null) {
            response.put("tool_calls", calls);
            response.put("tools", tools);
        }
        if (call.finish() != null) {
            response.put("finish", call.finish());
        }
        if (steps != null) {
            response.put("steps", steps);
        }
        return response;
    }

    private static long chars(Object text) {
        return text instanceof String s ? s.codePointCount(0, s.length()) : 0;
    }

    private static Map<String, Object> document(String tenantNow, String app, String suite,
            Map<String, Object> caseCompartment, Map<String, Object> setup, String digest,
            Map<String, Object> response, String recordedAt) {
        Map<String, Object> document = new TreeMap<>();
        document.put("recording_version", RECORDING_VERSION);
        document.put("source_tenant", tenantNow);
        document.put("app", app);
        document.put("suite", suite == null || suite.isEmpty() ? UNASSIGNED : suite);
        document.put("case", caseCompartment);
        document.put("setup", setup);
        document.put("setup_digest", digest);
        document.put("response", response);
        document.put("recorded_at", recordedAt);
        return document;
    }

    /** A compartment as JSON carries it: checked, and copied, so what is written was checked. */
    @SuppressWarnings("unchecked")
    private static Map<String, Object> compartment(Map<String, Object> given) {
        return (Map<String, Object>) Json.parse(Json.compact(given));
    }

    private void write(String tenantNow, Map<String, Object> document) throws IOException {
        long grown = writer.write(tenantNow, Json.file(document) + "\n");
        sizes.merge(tenantNow, grown, Long::sum);
    }

    private String tenantNow() {
        String found = production ? tenantFunction.get() : tenant;
        return found == null || found.isEmpty() ? null : found;
    }

    private static boolean sampledIn(Switch on) {
        return on.sample >= 1 || ThreadLocalRandom.current().nextDouble() < on.sample;
    }

    private boolean atCeiling(String tenantNow, Switch on) {
        if (stopped.contains(tenantNow)) {
            return true;
        }
        long size = sizes.getOrDefault(tenantNow, 0L);
        if (size < on.ceiling) {
            return false;
        }
        if (stopped.add(tenantNow)) {
            markCeiling(tenantNow, on.ceiling, size);
        }
        return true;
    }

    private void markCeiling(String tenantNow, long ceiling, long size) {
        Path directory = root.resolve(STORE).resolve(tenantNow).resolve(RECORDINGS);
        try {
            Files.createDirectories(directory);
            Path temporary = directory.resolve("." + CEILING_MARKER + "." + ProcessHandle.current().pid());
            Files.writeString(temporary, "{\"ceiling\": " + ceiling + ", \"size\": " + size + "}\n",
                    StandardCharsets.UTF_8);
            Files.move(temporary, directory.resolve(CEILING_MARKER),
                    StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE);
        } catch (IOException | RuntimeException ignored) {
            // A marker that cannot be written is not an error the application hears of.
        }
    }

    /** The class and method that made the call: the first frame outside the hooks and the SDKs. */
    private static String callSite() {
        return StackWalker.getInstance().walk(frames -> frames
                .filter(frame -> !foreign(frame.getClassName()))
                .findFirst()
                .map(frame -> frame.getClassName() + ":" + frame.getMethodName())
                .orElse(null));
    }

    private static boolean foreign(String name) {
        for (String prefix : List.of("dev.digline.", "java.", "javax.", "jdk.", "sun.", "kotlin.",
                "okhttp3.", "okio.", "com.openai.", "com.anthropic.", "software.amazon.")) {
            if (name.startsWith(prefix)) {
                return true;
            }
        }
        return false;
    }

    // ---------------------------------------------------------------- the episode

    /**
     * One turn of an agent, recorded as one recording with the calls made
     * inside it, written when it closes. {@code suite} may be {@code null};
     * {@code caseCompartment} is the input that started the turn, and its JSON
     * text is the answer's {@code input}.
     */
    public Episode episode(String suite, Map<String, Object> caseCompartment) {
        return episode(suite, caseCompartment, null);
    }

    /** An episode whose setup is given rather than derived from its calls. */
    public Episode episode(String suite, Map<String, Object> caseCompartment,
            Map<String, Object> setup) {
        return new Episode(this, suite, caseCompartment, setup);
    }

    /**
     * An episode, closed by try-with-resources. Off, it is an empty scope:
     * {@link #id()} is {@code null}, and {@link #output} keeps nothing.
     */
    public static final class Episode implements Scope {
        private final DiglineRecorder recorder;
        private final String suite;
        private final Map<String, Object> caseCompartment;
        private final Map<String, Object> setup;
        private final String site;
        private String id;
        private String parent;
        private String before;
        private Collector collector;
        private long started;
        private Object output;
        private boolean outputGiven;
        private boolean interrupted;
        private boolean closed;

        Episode(DiglineRecorder recorder, String suite, Map<String, Object> caseCompartment,
                Map<String, Object> setup) {
            this.recorder = recorder;
            this.suite = suite == null || suite.isEmpty() ? null : suite;
            this.caseCompartment = Objects.requireNonNull(caseCompartment, "case");
            this.setup = setup;
            this.site = recorder.on() && this.suite == null ? callSite() : null;
            if (!recorder.anyOn) {
                return;
            }
            this.id = hex(16);
            this.parent = CURRENT.get();
            Collector above = parent == null ? null : OPEN.get(parent);
            this.collector = new Collector(above != null ? above.sampledOut : !recorder.episodeSampledIn());
            OPEN.put(id, collector);
            this.before = parent;
            CURRENT.set(id);
            this.started = System.nanoTime();
        }

        /** The episode's id, 32 hexadecimal characters, or {@code null} while off. */
        public String id() {
            return id;
        }

        /**
         * The turn's final output: a {@code String}, or a {@code Map} for a
         * structured answer. The last one given is recorded; with none, the
         * text of the last call made inside the episode.
         */
        public void output(Object result) {
            if (id != null) {
                this.output = result;
                this.outputGiven = true;
            }
        }

        /**
         * Says the turn ended by an exception, so the recording holds what was
         * seen until then and says {@code interrupted}. Java's
         * try-with-resources does not tell {@code close()} why it closes, so
         * the application says it, in its {@code catch}.
         */
        public void interrupted() {
            this.interrupted = true;
        }

        @Override
        public void close() {
            if (id == null || closed) {
                return;
            }
            closed = true;
            double elapsedMs = (System.nanoTime() - started) / 1_000_000.0;
            restore(CURRENT, before);
            OPEN.remove(id);
            CLOSED.put(id, Boolean.TRUE);
            if (collector.sampledOut) {
                recorder.count("sampled out");
                return;
            }
            String reason;
            try {
                reason = recorder.recordEpisode(this, elapsedMs);
            } catch (RuntimeException | Error unexpected) {
                reason = "unexpected: " + unexpected.getClass().getSimpleName();
            }
            recorder.count(reason);
            if (parent != null) {
                Collector above = OPEN.get(parent);
                if (above != null) {
                    above.add(collector);
                }
            }
        }
    }

    private boolean episodeSampledIn() {
        try {
            String tenantNow = tenantNow();
            Switch on = tenantNow == null ? null : switches.get(tenantNow);
            return on == null || !on.on || sampledIn(on);
        } catch (RuntimeException unknown) {
            return true;
        }
    }

    private String recordEpisode(Episode episode, double elapsedMs) {
        String stage = "setup";
        try {
            List<Seen> calls = episode.collector.calls();
            Map<String, Object> setup;
            if (episode.setup != null) {
                setup = new TreeMap<>(episode.setup);
            } else {
                setup = new TreeMap<>();
                setup.put("child_setups", new ArrayList<>(episode.collector.digests()));
                String found = commit();
                if (found != null) {
                    setup.put("git_commit", found);
                }
            }
            stage = "not JSON";
            setup = compartment(setup);
            Map<String, Object> caseCompartment = compartment(episode.caseCompartment);
            String digest = setupDigest(setup);
            episode.collector.digest = digest;
            String question = Json.compact(caseCompartment);

            stage = "output";
            String text;
            String kind;
            if (episode.outputGiven) {
                if (episode.output instanceof String given) {
                    text = given;
                    kind = "text";
                } else if (episode.output instanceof Map<?, ?> given) {
                    text = Json.compact(rounded(given));
                    kind = "structured";
                } else {
                    return stage;
                }
            } else if (!calls.isEmpty()) {
                text = calls.get(calls.size() - 1).text;
                kind = "text";
            } else {
                return "no output";
            }

            List<Step> made = new ArrayList<>();
            boolean known = true;
            List<ToolCall> trajectory = new ArrayList<>();
            for (Seen seen : calls) {
                made.add(new Step(seen.finish, seen.calls));
                if (seen.calls == null) {
                    known = false;
                } else {
                    trajectory.addAll(seen.calls);
                }
            }
            List<Map<String, Object>> steps = stepsOf(made);
            long trajectoryChars = 0;
            for (ToolCall each : known ? trajectory : List.<ToolCall>of()) {
                Map<String, Object> written = each.asMap();
                trajectoryChars += chars(written.get("tool")) + chars(written.get("arguments"))
                        + chars(written.get("result"));
            }
            Map<String, Object> response = new TreeMap<>();
            if (chars(text) > MAX_RECORDED_CHARS || chars(question) > MAX_RECORDED_CHARS
                    || trajectoryChars > MAX_RECORDED_CHARS) {
                response.put("oversize", true);
                response.put("latency_ms", round(elapsedMs));
            } else {
                response.put("output", text);
                response.put("kind", kind);
                response.put("input", question);
                response.put("latency_ms", round(elapsedMs));
                if (known) {
                    List<Map<String, Object>> written = new ArrayList<>();
                    List<Object> names = new ArrayList<>();
                    for (ToolCall each : trajectory) {
                        written.add(each.asMap());
                        names.add(each.tool());
                    }
                    response.put("tool_calls", written);
                    response.put("tools", names);
                }
                if (!steps.isEmpty()) {
                    response.put("steps", steps);
                }
                String finish = lastFinish(made);
                if (finish != null) {
                    response.put("finish", finish);
                }
            }

            stage = "tenant";
            String tenantNow = tenantNow();
            if (tenantNow == null) {
                return stage;
            }
            Switch on = switches.get(tenantNow);
            if (on == null || !on.on) {
                return "off for this tenant";
            }
            if (atCeiling(tenantNow, on)) {
                return "ceiling";
            }

            stage = "not JSON";
            Map<String, Object> document = document(tenantNow, app, episode.suite, caseCompartment,
                    setup, digest, response, now());
            document.put("id", episode.id);
            if (episode.parent != null) {
                document.put("episode", episode.parent);
            }
            if (episode.site != null) {
                document.put("call_site", episode.site);
            }
            if (episode.interrupted) {
                document.put("interrupted", true);
            }
            long unrecorded = episode.collector.childrenUnrecorded();
            if (unrecorded > 0) {
                document.put("unrecorded_children", unrecorded);
            }
            stage = "writer";
            write(tenantNow, document);
        } catch (IOException | RuntimeException failed) {
            return stage;
        }
        return null;
    }

    private static String lastFinish(List<Step> made) {
        return made.isEmpty() ? null : made.get(made.size() - 1).finish();
    }

    /** The repository's commit, as digline reads it for a run, cached until the next look. */
    private String commit() {
        String[] cached = commit;
        if (cached == null) {
            String sha = git("rev-parse", "HEAD");
            String found = null;
            if (sha != null) {
                String status = git("status", "--porcelain");
                found = status != null && !status.isEmpty() ? sha + "-dirty" : sha;
            }
            cached = new String[] {found};
            commit = cached;
        }
        return cached[0];
    }

    private String git(String... args) {
        List<String> command = new ArrayList<>(List.of("git", "-C", root.toString()));
        command.addAll(List.of(args));
        try {
            Process process = new ProcessBuilder(command).redirectErrorStream(false).start();
            process.getOutputStream().close();
            String out;
            try (InputStream stdout = process.getInputStream()) {
                out = new String(stdout.readAllBytes(), StandardCharsets.UTF_8);
            }
            process.getErrorStream().close();
            if (!process.waitFor(10, TimeUnit.SECONDS)) {
                process.destroyForcibly();
                return null;
            }
            return process.exitValue() == 0 ? out.strip() : null;
        } catch (IOException notInstalled) {
            return null;
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            return null;
        }
    }

    /** One call to a model, as a trajectory sees it: its finish and the tools it asked for. */
    public record Step(String finish, List<ToolCall> toolCalls) {
    }

    /**
     * The steps of a trajectory, as digline's {@code steps_of} makes them: one
     * {@code model} step per call, with its finish, then one {@code tool} step
     * per tool call it asked for, indexed from 0.
     */
    public static List<Map<String, Object>> stepsOf(List<Step> calls) {
        List<Map<String, Object>> steps = new ArrayList<>();
        for (Step call : calls) {
            Map<String, Object> model = new TreeMap<>();
            model.put("index", steps.size());
            model.put("actor", "model");
            if (call.finish() != null) {
                model.put("finish", call.finish());
            }
            steps.add(model);
            for (ToolCall each : call.toolCalls() == null ? List.<ToolCall>of() : call.toolCalls()) {
                Map<String, Object> tool = new TreeMap<>(each.asMap());
                tool.put("index", steps.size());
                tool.put("actor", "tool");
                steps.add(tool);
            }
        }
        return steps;
    }

    private static final class Seen {
        final String digest;
        final String text;
        final String finish;
        final List<ToolCall> calls;

        Seen(String digest, String text, String finish, List<ToolCall> calls) {
            this.digest = digest;
            this.text = text;
            this.finish = finish;
            this.calls = calls;
        }
    }

    /** An open episode's children, as they arrive, from any thread. */
    private static final class Collector {
        final boolean sampledOut;
        private final List<Object> events = new ArrayList<>();
        private long unrecorded;
        volatile String digest;

        Collector(boolean sampledOut) {
            this.sampledOut = sampledOut;
        }

        synchronized void add(Object event) {
            if (event == null) {
                unrecorded++;
            } else {
                events.add(event);
            }
        }

        List<Seen> calls() {
            List<Object> seen;
            synchronized (this) {
                seen = new ArrayList<>(events);
            }
            List<Seen> found = new ArrayList<>();
            for (Object event : seen) {
                if (event instanceof Collector nested) {
                    found.addAll(nested.calls());
                } else {
                    found.add((Seen) event);
                }
            }
            return found;
        }

        long childrenUnrecorded() {
            List<Object> seen;
            long own;
            synchronized (this) {
                seen = new ArrayList<>(events);
                own = unrecorded;
            }
            for (Object event : seen) {
                if (event instanceof Collector nested) {
                    own += nested.childrenUnrecorded();
                }
            }
            return own;
        }

        /** The setup digests of the direct children, distinct and sorted. */
        Set<String> digests() {
            Set<String> found = new TreeSet<>();
            synchronized (this) {
                for (Object event : events) {
                    String digest = event instanceof Collector nested ? nested.digest : ((Seen) event).digest;
                    if (digest != null) {
                        found.add(digest);
                    }
                }
            }
            return found;
        }
    }

    // ---------------------------------------------------------------- the switch

    /** One tenant's switch, as read from its file or from the environment. */
    public static final class Switch {
        public final boolean on;
        public final double sample;
        public final String redact;
        public final long ceiling;
        public final double interval;
        public final boolean production;
        public final Set<String> declared;

        Switch(boolean on, double sample, long ceiling, double interval, boolean production,
                Set<String> declared) {
            this.on = on;
            this.sample = sample;
            this.redact = "none";
            this.ceiling = ceiling;
            this.interval = interval;
            this.production = production;
            this.declared = declared;
        }
    }

    /**
     * A switch file's text, or a {@link StartError} naming {@code where}, with
     * the sentences digline's {@code parse_switch} uses.
     */
    public static Switch parseSwitch(String text, String where, boolean production) {
        Map<String, Object> raw;
        try {
            raw = Toml.parse(text);
        } catch (IllegalArgumentException invalid) {
            throw new StartError(where + " is not valid TOML");
        }
        Set<String> unknown = new TreeSet<>(raw.keySet());
        unknown.removeAll(SWITCH_KEYS);
        if (!unknown.isEmpty()) {
            throw new StartError(where + " has keys the recorder does not read: "
                    + String.join(", ", unknown) + ". It reads " + String.join(", ", SWITCH_KEYS));
        }
        if (!(raw.get("on") instanceof Boolean on)) {
            throw new StartError(where + " must say on = true or on = false");
        }
        Object sample = raw.get("sample");
        if (sample != null && !(number(sample) && asDouble(sample) > 0 && asDouble(sample) <= 1)) {
            throw new StartError(where + ": sample must be a number above 0 and at most 1");
        }
        Object redact = raw.get("redact");
        if (redact != null && !"none".equals(redact)) {
            String said = pythonStr(redact);
            if (said.length() > 40) {
                said = said.substring(0, said.offsetByCodePoints(0, 40));
            }
            throw new StartError(where + ": redact = " + pythonRepr(said) + " is not implemented. "
                    + "This release implements redact = \"none\" alone (ADR 0058 §4)");
        }
        Object ceiling = raw.get("ceiling");
        if (ceiling != null && !(ceiling instanceof BigInteger whole && whole.signum() > 0)) {
            throw new StartError(where + ": ceiling must be a whole number of bytes, at least 1");
        }
        Object every = raw.get("interval");
        if (every != null && !(number(every) && asDouble(every) > 0)) {
            throw new StartError(where + ": interval must be a number of seconds above 0");
        }
        Object declaredProduction = raw.getOrDefault("production", Boolean.FALSE);
        if (!(declaredProduction instanceof Boolean said)) {
            throw new StartError(where + ": production must be true or false");
        }
        boolean held = production || said;
        if (held && on) {
            List<String> missing = new ArrayList<>();
            if (redact == null) {
                missing.add("no declared redaction (write redact = \"none\", the one this "
                        + "release implements)");
            }
            if (sample == null) {
                missing.add("no declared sampling (write sample = p, above 0 and at most 1)");
            }
            if (ceiling == null) {
                missing.add("no ceiling on the size of its recordings (write ceiling = N, in bytes)");
            }
            if (!missing.isEmpty()) {
                throw new StartError(where + " switches recording on in production with "
                        + String.join("; ", missing) + ". In production all three are declared "
                        + "(ADR 0058 §10)");
            }
        }
        long bytes = ceiling == null ? DEFAULT_CEILING
                : ((BigInteger) ceiling).min(BigInteger.valueOf(Long.MAX_VALUE)).longValue();
        return new Switch(on,
                sample == null ? DEFAULT_SAMPLE : asDouble(sample),
                bytes,
                every == null ? DEFAULT_INTERVAL : asDouble(every),
                said,
                Set.copyOf(raw.keySet()));
    }

    private static boolean number(Object value) {
        return value instanceof BigInteger || value instanceof Double;
    }

    private static double asDouble(Object value) {
        return value instanceof BigInteger whole ? whole.doubleValue() : (Double) value;
    }

    private static boolean switchedOn() {
        String value = System.getenv(ENVIRONMENT_VARIABLE);
        if (value == null || value.isEmpty() || value.equals("0")) {
            return false;
        }
        if (value.equals("1")) {
            return true;
        }
        throw new StartError(ENVIRONMENT_VARIABLE + " is set to a value that is neither 1 (record) "
                + "nor 0 or empty (do not record)");
    }

    private record Stamp(long modified, long size) {
    }

    private Map<String, Path> switchFiles() {
        Path store = root.resolve(STORE);
        if (!production) {
            return Map.of(tenant, store.resolve(tenant).resolve(SWITCH_FILE));
        }
        Map<String, Path> found = new HashMap<>();
        try (DirectoryStream<Path> entries = Files.newDirectoryStream(store)) {
            for (Path entry : entries) {
                Path candidate = entry.resolve(SWITCH_FILE);
                if (Files.isDirectory(entry) && Files.isRegularFile(candidate)) {
                    found.put(entry.getFileName().toString(), candidate);
                }
            }
        } catch (IOException | RuntimeException none) {
            // No .digline/ yet: no tenant has a switch.
        }
        return found;
    }

    private static Stamp stamp(Path path) {
        try {
            BasicFileAttributes seen = Files.readAttributes(path, BasicFileAttributes.class);
            return new Stamp(seen.lastModifiedTime().to(TimeUnit.NANOSECONDS), seen.size());
        } catch (IOException | RuntimeException absent) {
            return null;
        }
    }

    private void readSwitches(boolean starting) {
        Map<String, Switch> read = new HashMap<>();
        Map<String, Stamp> seen = new HashMap<>();
        Map<String, Stamp> before = stamps;
        for (Map.Entry<String, Path> entry : switchFiles().entrySet()) {
            Path path = entry.getValue();
            Stamp now = stamp(path);
            if (now == null) {
                continue;
            }
            seen.put(entry.getKey(), now);
            try {
                String text;
                try {
                    text = Files.readString(path, StandardCharsets.UTF_8);
                } catch (IOException | RuntimeException unreadable) {
                    throw new StartError(path + " cannot be read");
                }
                Switch found = parseSwitch(text, path.toString(), production);
                if (production && found.on && !writable(path.getParent())) {
                    throw new StartError(path + " switches recording on in production, and "
                            + path.getParent() + " is not a writable directory to put the "
                            + "recordings in (ADR 0058 §10)");
                }
                read.put(entry.getKey(), found);
            } catch (StartError invalid) {
                if (starting && production) {
                    throw invalid;
                }
                count("config invalid");
                if (!now.equals(before.get(entry.getKey()))) {
                    System.err.println("digline recorder: not recording for this tenant: "
                            + invalid.getMessage());
                }
            }
        }
        if (!production && seen.isEmpty() && switchedOn()) {
            read.put(tenant, new Switch(true, DEFAULT_SAMPLE, DEFAULT_CEILING, DEFAULT_INTERVAL,
                    false, Set.of()));
        }
        stamps = Map.copyOf(seen);
        switches = Map.copyOf(read);
        anyOn = read.values().stream().anyMatch(each -> each.on);
        interval = read.values().stream().mapToDouble(each -> each.interval).min()
                .orElse(DEFAULT_INTERVAL);
    }

    private static boolean writable(Path directory) {
        for (Path candidate = directory; candidate != null; candidate = candidate.getParent()) {
            if (Files.exists(candidate)) {
                return Files.isDirectory(candidate) && Files.isWritable(candidate)
                        && Files.isExecutable(candidate);
            }
        }
        return false;
    }

    private void lookIfDue() {
        if (System.nanoTime() - nextLook < 0) {
            return;
        }
        if (!lookLock.tryLock()) {
            return;
        }
        try {
            Map<String, Stamp> now = new HashMap<>();
            for (Map.Entry<String, Path> entry : switchFiles().entrySet()) {
                Stamp found = stamp(entry.getValue());
                if (found != null) {
                    now.put(entry.getKey(), found);
                }
            }
            if (!now.equals(stamps)) {
                readSwitches(false);
            }
            measure();
            commit = null;
        } catch (RuntimeException unexpected) {
            count("config invalid");
        } finally {
            nextLook = System.nanoTime() + nanos(interval);
            lookLock.unlock();
        }
    }

    private static long nanos(double seconds) {
        return (long) (seconds * 1_000_000_000L);
    }

    /** Each recording tenant's size, from the disk; a stopped tenant under its ceiling resumes. */
    private void measure() {
        for (Map.Entry<String, Switch> entry : switches.entrySet()) {
            if (!entry.getValue().on) {
                continue;
            }
            String name = entry.getKey();
            long size = recordingsSize(name);
            sizes.put(name, size);
            if (stopped.contains(name) && size < entry.getValue().ceiling) {
                stopped.remove(name);
                try {
                    Files.deleteIfExists(root.resolve(STORE).resolve(name).resolve(RECORDINGS)
                            .resolve(CEILING_MARKER));
                } catch (IOException | RuntimeException ignored) {
                    // The status reads a stale marker until the next look removes it.
                }
            }
        }
    }

    private long recordingsSize(String name) {
        long total = 0;
        Path directory = root.resolve(STORE).resolve(name).resolve(RECORDINGS);
        try (DirectoryStream<Path> folders = Files.newDirectoryStream(directory)) {
            for (Path folder : folders) {
                if (!Files.isDirectory(folder, LinkOption.NOFOLLOW_LINKS)) {
                    continue;
                }
                try (DirectoryStream<Path> files = Files.newDirectoryStream(folder)) {
                    for (Path item : files) {
                        String file = item.getFileName().toString();
                        if (file.endsWith(".json") && !file.startsWith(".")) {
                            total += Files.readAttributes(item, BasicFileAttributes.class,
                                    LinkOption.NOFOLLOW_LINKS).size();
                        }
                    }
                }
            }
        } catch (IOException | RuntimeException partial) {
            return total;
        }
        return total;
    }

    // ---------------------------------------------------------------- the writer

    /**
     * Files recordings under {@code .digline/<tenant>/recordings/j<pid>-<8 hex>/},
     * {@code 000001.json} and on: written to a temporary file whose name
     * starts with a dot, which no reader reads, and linked into place, which
     * fails rather than replace. Never fsynced, as digline's are not.
     */
    static final class Writer {
        private final Path root;
        private final Map<String, Place> places = new HashMap<>();

        Writer(Path root) {
            this.root = root;
        }

        private static final class Place {
            final Path directory;
            int number;

            Place(Path directory) {
                this.directory = directory;
            }
        }

        long write(String tenant, String payload) throws IOException {
            Path path = next(checked(tenant));
            Path temporary = Files.createTempFile(path.getParent(), ".tmp-", ".json");
            try {
                Files.writeString(temporary, payload, StandardCharsets.UTF_8);
                try {
                    Files.createLink(path, temporary);
                } catch (FileAlreadyExistsException taken) {
                    throw new IOException(path + " already exists: a recording is never written "
                            + "over another");
                }
            } finally {
                Files.deleteIfExists(temporary);
            }
            return Files.size(path);
        }

        private synchronized Path next(String tenant) throws IOException {
            Place place = places.get(tenant);
            if (place == null) {
                Path store = root.resolve(STORE);
                layout(store, tenant);
                Path directory = store.resolve(tenant).resolve(RECORDINGS)
                        .resolve("j" + ProcessHandle.current().pid() + "-" + hex(4));
                Files.createDirectories(directory.getParent());
                Files.createDirectory(directory);
                place = new Place(directory);
                places.put(tenant, place);
            }
            place.number++;
            return place.directory.resolve(String.format("%06d.json", place.number));
        }

        /** The layout digline makes before a tenant's first recording, so git ignores it. */
        private static void layout(Path store, String tenant) throws IOException {
            Files.createDirectories(store.resolve(tenant).resolve("baselines"));
            Files.createDirectories(store.resolve(tenant).resolve("runs"));
            create(store.resolve(".gitignore"), GITIGNORE);
            create(store.resolve(".gitattributes"), GITATTRIBUTES);
        }

        private static void create(Path path, String text) throws IOException {
            if (!Files.exists(path)) {
                try {
                    Files.writeString(path, text, StandardCharsets.UTF_8,
                            java.nio.file.StandardOpenOption.CREATE_NEW,
                            java.nio.file.StandardOpenOption.WRITE);
                } catch (FileAlreadyExistsException another) {
                    // Another process laid it out first, with the same text.
                }
            }
        }

        private static String checked(String tenant) {
            if (tenant.isEmpty() || tenant.equals(".") || tenant.equals("..") || tenant.contains("/")
                    || tenant.contains("\\") || tenant.contains("\0")) {
                throw new IllegalArgumentException("a tenant is a directory name");
            }
            return tenant;
        }
    }

    private static final SecureRandom RANDOM = new SecureRandom();

    private static String hex(int bytes) {
        byte[] drawn = new byte[bytes];
        RANDOM.nextBytes(drawn);
        StringBuilder out = new StringBuilder();
        for (byte each : drawn) {
            out.append(String.format("%02x", each));
        }
        return out.toString();
    }

    private static final DateTimeFormatter SECONDS =
            DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss").withZone(ZoneOffset.UTC);

    /**
     * Now, in the contract's one form: UTC, to the microsecond, with the
     * offset written {@code +00:00} and the fraction left out when it is zero,
     * as Python's {@code isoformat()} writes it. Never {@code Z}.
     */
    static String now() {
        return timestamp(Instant.now());
    }

    static String timestamp(Instant instant) {
        Instant micros = instant.truncatedTo(ChronoUnit.MICROS);
        int fraction = micros.getNano() / 1000;
        String seconds = SECONDS.format(micros);
        return fraction == 0 ? seconds + "+00:00" : String.format("%s.%06d+00:00", seconds, fraction);
    }

    // ---------------------------------------------------------------- digest and numbers

    /**
     * The setup's digest: the first 16 hexadecimal characters of the SHA-256
     * of the setup as Python's {@code json.dumps} writes it, keys sorted,
     * separators {@code ,} and {@code :}, non-ASCII escaped, and each float
     * written as a string in the form {@link #floatText} gives.
     */
    public static String setupDigest(Map<String, Object> setup) {
        String payload = Json.write(setup, Json.Mode.DIGEST, 0);
        try {
            byte[] hash = MessageDigest.getInstance("SHA-256")
                    .digest(payload.getBytes(StandardCharsets.UTF_8));
            StringBuilder hex = new StringBuilder();
            for (int i = 0; i < 8; i++) {
                hex.append(String.format("%02x", hash[i]));
            }
            return hex.toString();
        } catch (NoSuchAlgorithmException absent) {
            throw new IllegalStateException("the JDK has no SHA-256", absent);
        }
    }

    /**
     * A float as the digest writes it: the shortest digits that read back as
     * the same double, positional, no trailing zeros or point; {@code "0"}
     * for both zeros. digline's {@code float_text}.
     */
    public static String floatText(double value) {
        if (value == 0) {
            return "0";
        }
        return shortest(value).stripTrailingZeros().toPlainString();
    }

    /**
     * A double as Python's {@code repr} writes it, which is how digline writes
     * a float into a file: the shortest digits that read back, positional
     * from 1e-4 to below 1e16, else with an exponent of at least two digits.
     */
    public static String pythonRepr(double value) {
        if (Double.isNaN(value) || Double.isInfinite(value)) {
            throw new IllegalArgumentException("NaN and the infinities are not JSON");
        }
        if (value == 0) {
            return (1 / value < 0) ? "-0.0" : "0.0";
        }
        BigDecimal shortest = shortest(Math.abs(value)).stripTrailingZeros();
        String digits = shortest.unscaledValue().toString();
        int point = digits.length() - shortest.scale();
        StringBuilder out = new StringBuilder(value < 0 ? "-" : "");
        if (point <= -4 || point > 16) {
            out.append(digits.charAt(0));
            if (digits.length() > 1) {
                out.append('.').append(digits, 1, digits.length());
            }
            int exponent = point - 1;
            out.append('e').append(exponent < 0 ? '-' : '+');
            String magnitude = Integer.toString(Math.abs(exponent));
            out.append(magnitude.length() < 2 ? "0" + magnitude : magnitude);
        } else if (point <= 0) {
            out.append("0.").append("0".repeat(-point)).append(digits);
        } else if (point >= digits.length()) {
            out.append(digits).append("0".repeat(point - digits.length())).append(".0");
        } else {
            out.append(digits, 0, point).append('.').append(digits, point, digits.length());
        }
        return out.toString();
    }

    /**
     * The shortest decimal that reads back as {@code value}, and of those the
     * closest: what Python's {@code repr} finds. Searched rather than taken
     * from {@code Double.toString}, which gives two digits where one would
     * do, as {@code 4.9E-324} for Python's {@code 5e-324}.
     */
    static BigDecimal shortest(double value) {
        BigDecimal exact = new BigDecimal(value);
        for (int digits = 1; digits <= 17; digits++) {
            BigDecimal best = null;
            for (RoundingMode mode : new RoundingMode[] {RoundingMode.HALF_EVEN, RoundingMode.FLOOR,
                    RoundingMode.CEILING}) {
                BigDecimal candidate = exact.round(new MathContext(digits, mode));
                if (candidate.doubleValue() != value) {
                    continue;
                }
                if (best == null) {
                    best = candidate;
                } else {
                    int closer = candidate.subtract(exact).abs().compareTo(best.subtract(exact).abs());
                    if (closer < 0) {
                        best = candidate;
                    }
                }
            }
            if (best != null) {
                return best;
            }
        }
        return exact;
    }

    /** {@code round(value, 6)}, as digline keeps a number in its documents. */
    static double round(double value) {
        if (Double.isNaN(value) || Double.isInfinite(value)) {
            throw new IllegalArgumentException("NaN and the infinities are not JSON");
        }
        double rounded = new BigDecimal(value).setScale(FLOAT_PRECISION, RoundingMode.HALF_EVEN)
                .doubleValue();
        // A BigDecimal has no negative zero, and Python's round keeps the sign: -1e-9 is -0.0.
        return rounded == 0 ? Math.copySign(0.0, value) : rounded;
    }

    /** A value with every float rounded as digline's {@code canonical} rounds it. */
    static Object rounded(Object value) {
        if (value instanceof Double number) {
            return round(number);
        }
        if (value instanceof Float number) {
            return round(number.doubleValue());
        }
        if (value instanceof Map<?, ?> map) {
            Map<String, Object> found = new TreeMap<>(Json.CODE_POINTS);
            for (Map.Entry<?, ?> entry : map.entrySet()) {
                found.put(String.valueOf(entry.getKey()), rounded(entry.getValue()));
            }
            return found;
        }
        if (value instanceof List<?> list) {
            List<Object> found = new ArrayList<>();
            for (Object item : list) {
                found.add(rounded(item));
            }
            return found;
        }
        return value;
    }

    private static String pythonStr(Object value) {
        if (value instanceof Boolean said) {
            return said ? "True" : "False";
        }
        if (value instanceof Double number) {
            return Double.isNaN(number) ? "nan" : Double.isInfinite(number)
                    ? (number > 0 ? "inf" : "-inf") : pythonRepr(number);
        }
        return String.valueOf(value);
    }

    private static String pythonRepr(String text) {
        char quote = text.contains("'") && !text.contains("\"") ? '"' : '\'';
        StringBuilder out = new StringBuilder().append(quote);
        for (int i = 0; i < text.length(); i++) {
            char c = text.charAt(i);
            if (c == quote || c == '\\') {
                out.append('\\').append(c);
            } else if (c == '\n') {
                out.append("\\n");
            } else if (c == '\r') {
                out.append("\\r");
            } else if (c == '\t') {
                out.append("\\t");
            } else if (c < 0x20 || c == 0x7f) {
                out.append(String.format("\\x%02x", (int) c));
            } else {
                out.append(c);
            }
        }
        return out.append(quote).toString();
    }

    // ---------------------------------------------------------------- JSON

    /**
     * JSON as digline reads and writes it. A parsed object is a map whose keys
     * sort as Python sorts them, by code point; an integer is a
     * {@code Long}, or a {@code BigInteger} past it; a number with a point or
     * an exponent is a {@code Double}.
     */
    public static final class Json {

        /** Python's string order: by code point, not by UTF-16 unit. */
        static final Comparator<String> CODE_POINTS = (left, right) -> {
            int i = 0;
            int j = 0;
            while (i < left.length() && j < right.length()) {
                int a = left.codePointAt(i);
                int b = right.codePointAt(j);
                if (a != b) {
                    return Integer.compare(a, b);
                }
                i += Character.charCount(a);
                j += Character.charCount(b);
            }
            return Integer.compare(left.length() - i, right.length() - j);
        };

        enum Mode {
            /** {@code json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=False)} */
            COMPACT,
            /** {@code json.dumps(sort_keys=True, indent=2, ensure_ascii=False)} */
            FILE,
            /** The digest's text: compact, non-ASCII escaped, floats as strings. */
            DIGEST
        }

        private Json() {
        }

        /** Compact, keys sorted, non-ASCII as it is: a recorded response's {@code input}. */
        public static String compact(Object value) {
            return write(value, Mode.COMPACT, 0);
        }

        /** Indented by two, keys sorted, non-ASCII as it is: a recording's file, without its newline. */
        public static String file(Object value) {
            return write(value, Mode.FILE, 0);
        }

        static String write(Object value, Mode mode, int depth) {
            StringBuilder out = new StringBuilder();
            write(value, mode, depth, out);
            return out.toString();
        }

        private static void write(Object value, Mode mode, int depth, StringBuilder out) {
            if (value == null) {
                out.append("null");
            } else if (value instanceof String text) {
                string(text, mode != Mode.DIGEST, out);
            } else if (value instanceof Boolean said) {
                out.append(said ? "true" : "false");
            } else if (value instanceof Long || value instanceof Integer || value instanceof Short
                    || value instanceof Byte || value instanceof BigInteger) {
                out.append(value);
            } else if (value instanceof Double || value instanceof Float) {
                double number = ((Number) value).doubleValue();
                if (mode == Mode.DIGEST) {
                    if (Double.isNaN(number) || Double.isInfinite(number)) {
                        throw new IllegalArgumentException("NaN and the infinities are not JSON");
                    }
                    string(floatText(number), false, out);
                } else {
                    out.append(pythonRepr(number));
                }
            } else if (value instanceof Map<?, ?> map) {
                Map<String, Object> sorted = new TreeMap<>(CODE_POINTS);
                for (Map.Entry<?, ?> entry : map.entrySet()) {
                    if (!(entry.getKey() instanceof String key)) {
                        throw new IllegalArgumentException("a JSON object's keys are strings");
                    }
                    sorted.put(key, entry.getValue());
                }
                if (sorted.isEmpty()) {
                    out.append("{}");
                    return;
                }
                out.append('{');
                boolean first = true;
                for (Map.Entry<String, Object> entry : sorted.entrySet()) {
                    if (!first) {
                        out.append(',');
                    }
                    first = false;
                    newline(mode, depth + 1, out);
                    string(entry.getKey(), mode != Mode.DIGEST, out);
                    out.append(mode == Mode.FILE ? ": " : ":");
                    write(entry.getValue(), mode, depth + 1, out);
                }
                newline(mode, depth, out);
                out.append('}');
            } else if (value instanceof List<?> list) {
                if (list.isEmpty()) {
                    out.append("[]");
                    return;
                }
                out.append('[');
                for (int i = 0; i < list.size(); i++) {
                    if (i > 0) {
                        out.append(',');
                    }
                    newline(mode, depth + 1, out);
                    write(list.get(i), mode, depth + 1, out);
                }
                newline(mode, depth, out);
                out.append(']');
            } else {
                throw new IllegalArgumentException("JSON cannot carry a "
                        + value.getClass().getSimpleName() + " as it is");
            }
        }

        private static void newline(Mode mode, int depth, StringBuilder out) {
            if (mode == Mode.FILE) {
                out.append('\n').append("  ".repeat(depth));
            }
        }

        /**
         * A string as Python writes it: {@code "}, {@code \}, and the control
         * characters escaped, the five with short forms by them; with
         * {@code ascii}, also DEL and every unit past it, as {@code \}{@code uXXXX}.
         * Without it, a lone surrogate is refused, as UTF-8 cannot carry it.
         */
        private static void string(String text, boolean unicode, StringBuilder out) {
            out.append('"');
            for (int i = 0; i < text.length(); i++) {
                char c = text.charAt(i);
                switch (c) {
                    case '"' -> out.append("\\\"");
                    case '\\' -> out.append("\\\\");
                    case '\n' -> out.append("\\n");
                    case '\r' -> out.append("\\r");
                    case '\t' -> out.append("\\t");
                    case '\b' -> out.append("\\b");
                    case '\f' -> out.append("\\f");
                    default -> {
                        if (c < 0x20 || (!unicode && c >= 0x7f)) {
                            out.append(String.format("\\u%04x", (int) c));
                        } else {
                            if (Character.isSurrogate(c)) {
                                boolean paired = Character.isHighSurrogate(c) && i + 1 < text.length()
                                        && Character.isLowSurrogate(text.charAt(i + 1));
                                if (!paired) {
                                    throw new IllegalArgumentException("a lone surrogate is not UTF-8");
                                }
                                out.append(c).append(text.charAt(++i));
                                continue;
                            }
                            out.append(c);
                        }
                    }
                }
            }
            out.append('"');
        }

        /** One JSON value, strict: NaN, the infinities and trailing text are refused. */
        public static Object parse(String text) {
            Reader reader = new Reader(text);
            Object value = reader.value();
            reader.space();
            if (reader.at < text.length()) {
                throw new IllegalArgumentException("text after the JSON value");
            }
            return value;
        }

        private static final class Reader {
            private final String text;
            int at;

            Reader(String text) {
                this.text = text;
            }

            void space() {
                while (at < text.length() && " \t\n\r".indexOf(text.charAt(at)) >= 0) {
                    at++;
                }
            }

            private char peek() {
                if (at >= text.length()) {
                    throw new IllegalArgumentException("the JSON ends early");
                }
                return text.charAt(at);
            }

            private void expect(char c) {
                if (peek() != c) {
                    throw new IllegalArgumentException("expected '" + c + "' at " + at);
                }
                at++;
            }

            Object value() {
                space();
                char c = peek();
                if (c == '{') {
                    at++;
                    Map<String, Object> found = new TreeMap<>(CODE_POINTS);
                    space();
                    if (peek() == '}') {
                        at++;
                        return found;
                    }
                    while (true) {
                        space();
                        String key = string();
                        space();
                        expect(':');
                        found.put(key, value());
                        space();
                        if (peek() == ',') {
                            at++;
                            continue;
                        }
                        expect('}');
                        return found;
                    }
                }
                if (c == '[') {
                    at++;
                    List<Object> found = new ArrayList<>();
                    space();
                    if (peek() == ']') {
                        at++;
                        return found;
                    }
                    while (true) {
                        found.add(value());
                        space();
                        if (peek() == ',') {
                            at++;
                            continue;
                        }
                        expect(']');
                        return found;
                    }
                }
                if (c == '"') {
                    return string();
                }
                if (text.startsWith("true", at)) {
                    at += 4;
                    return Boolean.TRUE;
                }
                if (text.startsWith("false", at)) {
                    at += 5;
                    return Boolean.FALSE;
                }
                if (text.startsWith("null", at)) {
                    at += 4;
                    return null;
                }
                return number();
            }

            private Object number() {
                int start = at;
                if (at < text.length() && text.charAt(at) == '-') {
                    at++;
                }
                int digits = at;
                while (at < text.length() && Character.isDigit(text.charAt(at))) {
                    at++;
                }
                if (at == digits || (text.charAt(digits) == '0' && at - digits > 1)) {
                    throw new IllegalArgumentException("not a JSON number at " + start);
                }
                boolean real = false;
                if (at < text.length() && text.charAt(at) == '.') {
                    real = true;
                    at++;
                    int fraction = at;
                    while (at < text.length() && Character.isDigit(text.charAt(at))) {
                        at++;
                    }
                    if (at == fraction) {
                        throw new IllegalArgumentException("not a JSON number at " + start);
                    }
                }
                if (at < text.length() && (text.charAt(at) == 'e' || text.charAt(at) == 'E')) {
                    real = true;
                    at++;
                    if (at < text.length() && (text.charAt(at) == '+' || text.charAt(at) == '-')) {
                        at++;
                    }
                    int exponent = at;
                    while (at < text.length() && Character.isDigit(text.charAt(at))) {
                        at++;
                    }
                    if (at == exponent) {
                        throw new IllegalArgumentException("not a JSON number at " + start);
                    }
                }
                String written = text.substring(start, at);
                if (real) {
                    double number = Double.parseDouble(written);
                    if (Double.isInfinite(number)) {
                        throw new IllegalArgumentException("a JSON number past a double");
                    }
                    return number;
                }
                BigInteger whole = new BigInteger(written);
                return whole.bitLength() < 64 ? (Object) whole.longValue() : whole;
            }

            private String string() {
                expect('"');
                StringBuilder out = new StringBuilder();
                while (true) {
                    char c = peek();
                    at++;
                    if (c == '"') {
                        return out.toString();
                    }
                    if (c < 0x20) {
                        throw new IllegalArgumentException("a control character in a JSON string");
                    }
                    if (c != '\\') {
                        out.append(c);
                        continue;
                    }
                    char escaped = peek();
                    at++;
                    switch (escaped) {
                        case '"' -> out.append('"');
                        case '\\' -> out.append('\\');
                        case '/' -> out.append('/');
                        case 'b' -> out.append('\b');
                        case 'f' -> out.append('\f');
                        case 'n' -> out.append('\n');
                        case 'r' -> out.append('\r');
                        case 't' -> out.append('\t');
                        case 'u' -> {
                            if (at + 4 > text.length()) {
                                throw new IllegalArgumentException("a short \\u escape");
                            }
                            out.append((char) Integer.parseInt(text.substring(at, at + 4), 16));
                            at += 4;
                        }
                        default -> throw new IllegalArgumentException("an unknown escape");
                    }
                }
            }
        }
    }

    // ---------------------------------------------------------------- TOML, as much as a switch holds

    /**
     * The TOML a switch file holds: {@code key = value} lines, comments and
     * blank lines; booleans, integers, floats and strings; and a table's
     * header, read as a key the switch then refuses by name, as digline's
     * reader does. An array, an inline table, a date or a dotted key is
     * refused here as not valid, where digline's reader reads it and then
     * refuses the key or its type: either way the switch is not read, and
     * the sentence differs.
     */
    static final class Toml {
        private Toml() {
        }

        static Map<String, Object> parse(String text) {
            Map<String, Object> found = new LinkedHashMap<>();
            Map<String, Object> into = found;
            for (String line : text.split("\n", -1)) {
                String stripped = withoutComment(line).strip();
                if (stripped.isEmpty()) {
                    continue;
                }
                if (stripped.startsWith("[") && stripped.endsWith("]") && !stripped.startsWith("[[")) {
                    // A table: a key of the file's top level, which the switch then refuses by name.
                    String name = stripped.substring(1, stripped.length() - 1).strip();
                    if (!name.matches("[A-Za-z0-9_-]+") || found.containsKey(name)) {
                        throw new IllegalArgumentException("not a table a switch reads");
                    }
                    into = new LinkedHashMap<>();
                    found.put(name, into);
                    continue;
                }
                int equals = stripped.indexOf('=');
                if (equals < 1) {
                    throw new IllegalArgumentException("not a key = value line");
                }
                String key = stripped.substring(0, equals).strip();
                if (key.startsWith("\"") && key.endsWith("\"") && key.length() >= 2) {
                    key = (String) value(key);
                } else if (!key.matches("[A-Za-z0-9_-]+")) {
                    throw new IllegalArgumentException("not a bare key");
                }
                if (into.containsKey(key)) {
                    throw new IllegalArgumentException("a key defined twice");
                }
                into.put(key, value(stripped.substring(equals + 1).strip()));
            }
            return found;
        }

        private static String withoutComment(String line) {
            boolean quoted = false;
            char quote = 0;
            for (int i = 0; i < line.length(); i++) {
                char c = line.charAt(i);
                if (quoted) {
                    if (c == '\\' && quote == '"') {
                        i++;
                    } else if (c == quote) {
                        quoted = false;
                    }
                } else if (c == '"' || c == '\'') {
                    quoted = true;
                    quote = c;
                } else if (c == '#') {
                    return line.substring(0, i);
                }
            }
            return line;
        }

        private static Object value(String written) {
            if (written.equals("true")) {
                return Boolean.TRUE;
            }
            if (written.equals("false")) {
                return Boolean.FALSE;
            }
            if (written.length() >= 2 && written.startsWith("'") && written.endsWith("'")) {
                String inside = written.substring(1, written.length() - 1);
                if (inside.contains("'")) {
                    throw new IllegalArgumentException("not a literal string");
                }
                return inside;
            }
            if (written.length() >= 2 && written.startsWith("\"") && written.endsWith("\"")) {
                Object parsed = Json.parse(written);
                return parsed;
            }
            String plain = written.replace("_", "");
            if (written.contains("__") || written.startsWith("_") || written.endsWith("_")) {
                throw new IllegalArgumentException("not a number");
            }
            if (plain.matches("[+-]?(inf|nan)")) {
                return plain.endsWith("nan") ? Double.NaN
                        : plain.startsWith("-") ? Double.NEGATIVE_INFINITY : Double.POSITIVE_INFINITY;
            }
            if (plain.matches("0x[0-9A-Fa-f]+")) {
                return new BigInteger(plain.substring(2), 16);
            }
            if (plain.matches("0o[0-7]+")) {
                return new BigInteger(plain.substring(2), 8);
            }
            if (plain.matches("0b[01]+")) {
                return new BigInteger(plain.substring(2), 2);
            }
            if (plain.matches("[+-]?(0|[1-9][0-9]*)")) {
                return new BigInteger(plain.startsWith("+") ? plain.substring(1) : plain);
            }
            if (plain.matches("[+-]?(0|[1-9][0-9]*)(\\.[0-9]+)?([eE][+-]?[0-9]+)?")) {
                return Double.parseDouble(plain);
            }
            throw new IllegalArgumentException("not a value a switch holds");
        }
    }
}
