"""Launch the target app and capture a bounded startup observation; no login actions."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import time

parser = argparse.ArgumentParser()
parser.add_argument("--serial", required=True)
parser.add_argument("--name", required=True)
parser.add_argument("--seconds", type=int, default=20)
parser.add_argument("--user", type=int, default=0)
args = parser.parse_args()
if not re.fullmatch(r"[a-zA-Z0-9_-]+", args.name):
    raise SystemExit("Invalid observation name")
root = Path(__file__).resolve().parent
output = root / "logs"
output.mkdir(exist_ok=True)
adb = ["adb", "-s", args.serial]
flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

def call(*command, check=True):
    result = subprocess.run(adb + list(command), capture_output=True, timeout=30,
                            creationflags=flags, check=check)
    return result.stdout.decode("utf-8", errors="replace")

packages = call("shell", "pm", "list", "packages", "--user", str(args.user), "-U", "cn.gov.pbc.dcep")
uid_match = re.search(r"^package:cn\.gov\.pbc\.dcep\s+uid:(\d+)", packages, re.MULTILINE)
if not uid_match:
    raise SystemExit("Target app is not installed for the selected Android user")
target_uid = uid_match.group(1)
hook_file = output / (args.name + "-hooks.txt")
app_file = output / (args.name + "-app.txt")
hook_stream = hook_file.open("wb")
app_stream = app_file.open("wb")
hook_capture = subprocess.Popen(adb + ["logcat", "-v", "threadtime", "-T", "1",
    "ShuziStartupCompat:I", "ShuziStartupCompatNative:I", "AndroidRuntime:E", "libc:F", "*:S"],
    stdout=hook_stream, stderr=subprocess.DEVNULL, creationflags=flags)
app_capture = subprocess.Popen(adb + ["logcat", "-v", "threadtime", "--uid=" + target_uid, "-T", "1"],
    stdout=app_stream, stderr=subprocess.DEVNULL, creationflags=flags)
samples = []
try:
    call("shell", "am", "force-stop", "--user", str(args.user), "cn.gov.pbc.dcep")
    start = time.monotonic()
    print(call("shell", "am", "start", "--user", str(args.user), "-W", "-n",
               "cn.gov.pbc.dcep/.DcepLauncherActivity"), flush=True)
    for elapsed in range(5, args.seconds + 1, 5):
        time.sleep(max(0, elapsed - (time.monotonic() - start)))
        pid = call("shell", "pidof", "cn.gov.pbc.dcep", check=False).strip()
        sample = {"elapsed_seconds": elapsed, "main_pid": pid}
        samples.append(sample)
        print(json.dumps(sample), flush=True)
    activity = call("shell", "dumpsys", "activity", "activities")
    focus = [line.strip() for line in activity.splitlines() if "topResumedActivity=" in line]
    print(json.dumps({"focus": focus}), flush=True)
    (output / (args.name + "-exit-info.txt")).write_text(
        call("shell", "dumpsys", "activity", "exit-info", "cn.gov.pbc.dcep"), encoding="utf-8")
    (output / (args.name + "-result.json")).write_text(
        json.dumps({"samples": samples, "focus": focus}, indent=2), encoding="utf-8")
finally:
    for process in [hook_capture, app_capture]:
        process.terminate()
        process.wait(timeout=5)
    hook_stream.close()
    app_stream.close()
for line in hook_file.read_text(encoding="utf-8", errors="replace").splitlines():
    if "ShuziStartupCompat" in line or "Fatal signal" in line or "FATAL EXCEPTION" in line:
        print(line)
