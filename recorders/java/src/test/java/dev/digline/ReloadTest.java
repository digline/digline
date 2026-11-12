package dev.digline;

import static org.junit.jupiter.api.Assertions.assertNotSame;
import static org.junit.jupiter.api.Assertions.assertSame;

import java.net.URL;
import java.net.URLClassLoader;
import org.junit.jupiter.api.Test;
import software.amazon.awssdk.core.interceptor.ExecutionAttribute;

/**
 * The hooks loaded again while the SDKs stay loaded, as a framework's dev mode
 * does on a reload: digline's classes come from a class loader of their own each
 * time, the SDKs' from the one they were first loaded by.
 */
class ReloadTest {

    /** Loads digline's classes itself, and leaves everything else to its parent. */
    static final class Reloading extends URLClassLoader {
        Reloading(URL classes, ClassLoader parent) {
            super(new URL[] {classes}, parent);
        }

        @Override
        protected Class<?> loadClass(String name, boolean resolve) throws ClassNotFoundException {
            if (!name.startsWith("dev.digline.")) {
                return super.loadClass(name, resolve);
            }
            synchronized (getClassLoadingLock(name)) {
                Class<?> loaded = findLoadedClass(name);
                if (loaded == null) {
                    loaded = findClass(name);
                }
                if (resolve) {
                    resolveClass(loaded);
                }
                return loaded;
            }
        }
    }

    @Test
    void eachHookInitialisesWhenItsClassIsLoadedAgain() throws Exception {
        URL classes = DiglineAws.class.getProtectionDomain().getCodeSource().getLocation();
        ClassLoader parent = ReloadTest.class.getClassLoader();
        for (String hook : new String[] {"dev.digline.DiglineAws", "dev.digline.DiglineAnthropic",
                "dev.digline.DiglineOkHttp", "dev.digline.DiglineRecorder"}) {
            Class<?> first;
            Class<?> second;
            try (Reloading one = new Reloading(classes, parent);
                    Reloading two = new Reloading(classes, parent)) {
                // initialize = true runs each load's static initialiser.
                first = Class.forName(hook, true, one);
                second = Class.forName(hook, true, two);
            }
            assertNotSame(first, second, hook + " was not loaded twice");
            assertSame(ExecutionAttribute.class,
                    Class.forName(ExecutionAttribute.class.getName(), false, first.getClassLoader()),
                    "the SDK was loaded again with " + hook + ", so its registry was not shared");
        }
    }
}
