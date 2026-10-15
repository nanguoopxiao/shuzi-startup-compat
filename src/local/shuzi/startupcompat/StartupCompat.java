package local.shuzi.startupcompat;

import android.content.pm.PackageInfo;
import android.os.Process;
import android.util.Log;
import java.io.File;
import java.io.FileInputStream;
import java.security.MessageDigest;
import de.robv.android.xposed.IXposedHookLoadPackage;
import de.robv.android.xposed.XposedBridge;
import de.robv.android.xposed.XposedHelpers;
import de.robv.android.xposed.callbacks.XC_LoadPackage;

/** Guarded, process-local compatibility experiment for one verified app build. */
public final class StartupCompat implements IXposedHookLoadPackage {
    private static final String TARGET = "cn.gov.pbc.dcep";
    private static final String TAG = "ShuziStartupCompat";
    private static final String LIBRARY_SHA256 =
            "69e8cfdfb7c53909fe91a96227861da41944efe0868011dca7306bfbe8620ffe";
    private static native void armNative();

    @Override
    public void handleLoadPackage(XC_LoadPackage.LoadPackageParam pkg) {
        if (!TARGET.equals(pkg.packageName)) return;
        if (!(TARGET.equals(pkg.processName)
                || (TARGET + ":tools").equals(pkg.processName)
                || (TARGET + ":push").equals(pkg.processName))) return;
        try {
            Class<?> activityThread = XposedHelpers.findClass("android.app.ActivityThread", null);
            Object manager = XposedHelpers.callStaticMethod(activityThread, "getPackageManager");
            PackageInfo info = (PackageInfo) XposedHelpers.callMethod(manager, "getPackageInfo",
                    TARGET, 0L, Process.myUid() / 100000);
            if (info == null || info.getLongVersionCode() != 204
                    || !"2.1.0.1".equals(info.versionName)) {
                log("unsupported app version; native component not loaded");
                return;
            }
            if (pkg.appInfo == null || pkg.appInfo.nativeLibraryDir == null) return;
            File original = new File(pkg.appInfo.nativeLibraryDir, "libDexHelper.so");
            if (!LIBRARY_SHA256.equals(sha256(original))) {
                log("original library hash mismatch; native component not loaded");
                return;
            }
            System.loadLibrary("shuzi");
            armNative();
            log("armed v0.2.1 for verified 2.1.0.1/204, process=" + pkg.processName);
        } catch (Throwable error) {
            log("setup skipped: " + error.getClass().getSimpleName() + ": " + error.getMessage());
        }
    }

    private static String sha256(File file) throws Exception {
        MessageDigest hash = MessageDigest.getInstance("SHA-256");
        try (FileInputStream stream = new FileInputStream(file)) {
            byte[] buffer = new byte[32768];
            int count;
            while ((count = stream.read(buffer)) != -1) hash.update(buffer, 0, count);
        }
        char[] hex = "0123456789abcdef".toCharArray();
        byte[] digest = hash.digest();
        char[] result = new char[digest.length * 2];
        for (int i = 0; i < digest.length; i++) {
            result[i * 2] = hex[(digest[i] & 255) >>> 4];
            result[i * 2 + 1] = hex[digest[i] & 15];
        }
        return new String(result);
    }

    private static void log(String message) {
        Log.i(TAG, message);
        XposedBridge.log(TAG + ": " + message);
    }
}
