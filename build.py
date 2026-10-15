"""Build on Windows with Android SDK 35, a JDK, and a WSL AArch64 C toolchain."""
from pathlib import Path
import hashlib
import os
import subprocess
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parent
sdk_path = os.environ.get("SHUZI_ANDROID_SDK") or os.environ.get("ANDROID_SDK_ROOT") or os.environ.get("ANDROID_HOME")
java_path = os.environ.get("SHUZI_JAVA_HOME") or os.environ.get("JAVA_HOME")
if not sdk_path or not java_path:
    raise SystemExit("Set SHUZI_ANDROID_SDK (or ANDROID_HOME) and SHUZI_JAVA_HOME (or JAVA_HOME); see README.md")
SDK = Path(sdk_path)
JAVA = Path(java_path)
TOOLS = SDK / "build-tools/35.0.0"
ANDROID = SDK / "platforms/android-35/android.jar"
API = ROOT / "deps/xposed-api-82.jar"
API_HASH = "f48c635f1c7469fdec0e00ad2ea0b7a6b2f5b55065784a35b7ca3a84615e8e25"
OUT = ROOT / "build"
DIST = ROOT / "dist"
SIGNING = ROOT / ".signing"
PASSWORD = "android"


def run(*args):
    subprocess.run([str(arg) for arg in args], cwd=ROOT, check=True)


for directory in [OUT, DIST, SIGNING, API.parent, OUT / "classes", OUT / "dex"]:
    directory.mkdir(parents=True, exist_ok=True)

# Remove only generated class files; do not package obsolete anonymous Java hook classes.
for file in (OUT / "classes").rglob("*.class"):
    file.unlink()

def wsl_path(path):
    value = str(path.resolve()).replace("\\", "/")
    return "/mnt/" + value[0].lower() + value[2:]

native_out = OUT / "libshuzi.so"
native_libs = Path(os.environ.get("SHUZI_ANDROID_LIBS", ROOT / "deps/android-lib64"))
for filename in ["libc.so", "libdl.so", "liblog.so"]:
    if not (native_libs / filename).is_file():
        raise SystemExit("Missing Android link library: " + str(native_libs / filename))
compiler = os.environ.get("SHUZI_CROSS_CC", "aarch64-linux-gnu-gcc")
host_libraries = os.environ.get("SHUZI_CROSS_HOST_LIBS")
wsl_command = ["wsl.exe", "-d", os.environ.get("SHUZI_WSL_DISTRO", "Ubuntu"), "--exec"]
if host_libraries:
    wsl_command.extend(["env", "LD_LIBRARY_PATH=" + host_libraries])
run(*wsl_command, compiler,
    "-std=c11", "-O2", "-fPIC", "-fvisibility=hidden", "-fno-stack-protector", "-fno-builtin",
    "-shared", "-nostdlib", "-Wl,-soname,libshuzi.so", "-Wl,--hash-style=both", "-Wl,-z,max-page-size=16384",
    wsl_path(ROOT / "native/startup_compat.c"), "-L" + wsl_path(native_libs),
    "-Wl,--no-as-needed", "-lc", "-ldl", "-llog", "-o", wsl_path(native_out))
if not API.exists():
    url = "https://api.xposed.info/de/robv/android/xposed/api/82/api-82.jar"
    with urllib.request.urlopen(url, timeout=30) as response:
        API.write_bytes(response.read())
if hashlib.sha256(API.read_bytes()).hexdigest() != API_HASH:
    raise SystemExit("Unexpected Xposed API hash")

sources = list((ROOT / "src").rglob("*.java"))
run(JAVA / "bin/javac.exe", "-encoding", "UTF-8", "-source", "8", "-target", "8",
    "-classpath", os.pathsep.join([str(ANDROID), str(API)]), "-d", OUT / "classes", *sources)
with zipfile.ZipFile(OUT / "module-classes.jar", "w") as jar:
    for file in (OUT / "classes").rglob("*.class"):
        jar.write(file, file.relative_to(OUT / "classes").as_posix())
run(JAVA / "bin/java.exe", "-cp", TOOLS / "lib/d8.jar", "com.android.tools.r8.D8",
    "--release", "--min-api", "27", "--lib", ANDROID, "--classpath", API,
    "--output", OUT / "dex", OUT / "module-classes.jar")
run(TOOLS / "aapt2.exe", "compile", "--dir", ROOT / "res", "-o", OUT / "resources.zip")
run(TOOLS / "aapt2.exe", "link", "--manifest", ROOT / "AndroidManifest.xml",
    "-I", ANDROID, "-A", ROOT / "assets", "-o", OUT / "unsigned.apk", OUT / "resources.zip")
with zipfile.ZipFile(OUT / "unsigned.apk", "a", compression=zipfile.ZIP_STORED) as apk:
    apk.write(OUT / "dex/classes.dex", "classes.dex")
    apk.write(native_out, "lib/arm64-v8a/libshuzi.so")
run(TOOLS / "zipalign.exe", "-f", "4", OUT / "unsigned.apk", OUT / "aligned.apk")
key = Path(os.environ.get("SHUZI_KEYSTORE", SIGNING / "local-development.p12"))
key.parent.mkdir(parents=True, exist_ok=True)
if not key.exists():
    run(JAVA / "bin/keytool.exe", "-genkeypair", "-keystore", key, "-storetype", "PKCS12",
        "-storepass", PASSWORD, "-keypass", PASSWORD, "-alias", "shuzi-local",
        "-keyalg", "RSA", "-keysize", "3072", "-validity", "3650",
        "-dname", "CN=Shuzi Local Compatibility Development", "-noprompt")
apk = DIST / "shuzi-startup-compat-0.2.1.apk"
run(JAVA / "bin/java.exe", "-jar", TOOLS / "lib/apksigner.jar", "sign",
    "--ks", key, "--ks-key-alias", "shuzi-local", "--ks-pass", "pass:" + PASSWORD,
    "--out", apk, OUT / "aligned.apk")
run(JAVA / "bin/java.exe", "-jar", TOOLS / "lib/apksigner.jar", "verify", "--verbose", apk)
print("APK:", apk)
print("SHA256:", hashlib.sha256(apk.read_bytes()).hexdigest())
