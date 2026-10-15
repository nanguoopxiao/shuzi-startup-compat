# 数字人民币启动兼容 · LSPosed

针对数字人民币 **2.1.0.1（versionCode 204）/ arm64-v8a** 的非官方启动兼容实验模块。当前模块版本为 **0.2.1**，包名为 `local.shuzi.startupcompat`。

在已验证的环境中，应用加固库因 Root / Xposed 类环境检测主动终止进程。本模块在严格校验目标版本及库内容后，将已确认的终止分支转入加固库原有的报告路径。

**适配范围严格限定。它处理当前构建的启动强退，不保证登录、支付或其他服务端风控通过，也不是通用 Root 隐藏方案。**

## 下载与启用

从 [GitHub Releases](https://github.com/nanguoopxiao/shuzi-startup-compat/releases) 下载 `shuzi-startup-compat-0.2.1.apk`。

1. 安装模块 APK。
2. 在 LSPosed 中启用“数字人民币启动兼容”。
3. 作用域仅勾选“数字人民币”（`cn.gov.pbc.dcep`）。
4. 强行停止数字人民币后重新打开，无需清除应用数据。

模块依赖可工作的 LSPosed / Zygisk 环境。模块运行时不调用 `su`，无需给数字人民币授予 Root 权限；验证时 SELinux 保持 **Enforcing**。

## 适配与验证

| 项目 | 范围 |
| --- | --- |
| 数字人民币版本 | `2.1.0.1` / `204` |
| ABI | `arm64-v8a` |
| 实测系统 | 一台 Android 16 设备 |
| 实测框架 | LSPosed `2.0.1 (7639)` / Zygisk Next `1.3.4` |
| 启动验证 | 两次冷启动通过，其中一次连续观察 60 秒 |
| 界面观察 | 登录页正常显示，之后观察到主界面进程仍在运行 |
| 未验证 | 完整登录、支付、其他机型和 MultiApp 分身 |

应用版本、原始库哈希或指令不匹配时，模块会跳过处理。更新数字人民币后需要重新核对，不能保证继续适用。

## 工作方式

- 仅处理目标应用的主进程、`:push` 和 `:tools` 进程。
- 校验版本名、版本号以及原始 `libDexHelper.so` 的 SHA-256。
- 使用 LSPosed 的 native 库加载回调，确认 `JNI_OnLoad` 位置及全部 9 处原始指令。
- 校验全部通过后，在当前应用进程的私有内存中调整分支，并恢复内存页权限。
- 涉及已确认的 `0x888`、`0x88c`、`0x79c` 终止路径，以及守护子进程提前向主进程发送 `SIGKILL` 的路径。

原始 APK、原始 so 文件与系统 SELinux 策略均不修改。进程结束后内存改动消失。

匹配的原始库 SHA-256：

```text
69e8cfdfb7c53909fe91a96227861da41944efe0868011dca7306bfbe8620ffe
```

## 撤销

停用或卸载本模块，再强行停止并重新打开数字人民币。不要清除数字人民币的数据。

## 源码

- `src/local/shuzi/startupcompat/StartupCompat.java`：目标范围、版本与原始库哈希校验。
- `native/startup_compat.c`：native 加载回调、指令校验、内存分支调整。
- `AndroidManifest.xml`、`assets/`、`res/`：模块声明、入口和推荐作用域。
- `build.py`：参考构建脚本。
- `verify_startup.py`：有界启动观察工具。

## 参考构建环境

当前构建方式是 **Windows + Python 3 + JDK 21 + Android SDK 35 + WSL Ubuntu 的 AArch64 GCC 交叉工具链**。native 库采用最小 bionic ABI 声明，不依赖 GNU libc 或 C++ 运行库。

Android SDK 需安装 `platforms;android-35` 与 `build-tools;35.0.0`。另需准备来自 Android arm64 系统的 `libc.so`、`libdl.so`、`liblog.so` 作为链接输入，放入 `deps/android-lib64/`；它们不会被打入模块 APK。例如，在自己的已连接测试设备上获取：

```powershell
New-Item -ItemType Directory -Force deps/android-lib64
adb pull /apex/com.android.runtime/lib64/bionic/libc.so deps/android-lib64/libc.so
adb pull /apex/com.android.runtime/lib64/bionic/libdl.so deps/android-lib64/libdl.so
adb pull /system/lib64/liblog.so deps/android-lib64/liblog.so
```

配置 SDK / JDK 后构建，路径请按本机安装位置填写：

```powershell
$env:SHUZI_ANDROID_SDK = 'C:\Android\Sdk'
$env:SHUZI_JAVA_HOME = 'C:\Java\jdk-21'
$env:SHUZI_WSL_DISTRO = 'Ubuntu'
$env:SHUZI_CROSS_CC = '/usr/bin/aarch64-linux-gnu-gcc'
python build.py
```

可选变量：`SHUZI_ANDROID_LIBS` 指定 Android 链接库目录；`SHUZI_CROSS_HOST_LIBS` 指定自包含交叉工具链的 WSL 宿主共享库搜索路径；`SHUZI_KEYSTORE` 指定本地开发签名文件。

脚本从 Xposed 官方 Maven 仓库获取 API 82，并固定校验 SHA-256。API 只用于编译，不打入 APK。输出位于 `dist/`。

默认会在 `.signing/` 创建本地开发签名。发布版的签名私钥不在仓库中，自行构建的 APK 通常不能覆盖安装发布版；更换签名前需卸载旧的兼容模块。

## 启动观察

```powershell
python verify_startup.py --serial YOUR_ADB_SERIAL --name check --seconds 20
```

该工具会强行停止并重新启动指定设备机主用户的数字人民币，然后采集进程及日志；不会执行登录。`--user` 可指定 Android 用户，但分身未经过实测。

日志保存在被 Git 忽略的 `logs/` 目录。应用日志可能含请求头和设备信息，请不要将原始日志直接发到公开 Issue。

## 发布校验

实机验证的 `v0.2.1` APK SHA-256：

```text
96a86c3a6e41ed83a8dd61d358d40faa30ab89c453848a06cd5136047c8d6e69
```

Release 同时提供 `SHA256SUMS.txt`。公开内容只包含本模块源码与模块 APK。

## 框架接口参考

- [LSPosed Native Hook](https://github.com/LSPosed/LSPosed/wiki/Native-Hook)
- [XposedHelpers API](https://api.xposed.info/reference/de/robv/android/xposed/XposedHelpers.html)
