/*
 * Private ARM64 compatibility experiment. Does not alter the APK or system policy.
 * Native callback ABI: https://github.com/LSPosed/LSPosed/wiki/Native-Hook
 * Minimal bionic ABI declarations keep this library independent of a C++ runtime.
 */
typedef unsigned int u32;
typedef unsigned long uptr;
typedef unsigned long usize;
typedef struct NativeFile NativeFile;
typedef struct { const char *name; void *base; const char *symbol; void *address; } DlInfo;
extern void *dlsym(void *, const char *);
extern int dladdr(const void *, DlInfo *);
extern int strcmp(const char *, const char *);
extern usize strlen(const char *);
extern NativeFile *fopen(const char *, const char *);
extern char *fgets(char *, int, NativeFile *);
extern int fclose(NativeFile *);
extern int sscanf(const char *, const char *, ...);
extern int getpagesize(void);
extern int mprotect(void *, usize, int);
extern int __android_log_print(int, const char *, const char *, ...);

typedef int (*Hook)(void *, void *, void **);
typedef int (*Unhook)(void *);
typedef void (*LibraryCallback)(const char *, void *);
typedef struct { u32 version; Hook hook_func; Unhook unhook_func; } NativeApi;
#define EXPORT __attribute__((visibility("default"), used))
#define TAG "ShuziStartupCompatNative"
#define LOG(...) __android_log_print(4, TAG, __VA_ARGS__)
#define COUNT(a) (sizeof(a) / sizeof((a)[0]))
_Static_assert(sizeof(void *) == 8, "ARM64 only");

typedef struct { uptr offset; u32 original; u32 report_branch; } Site;
/* Each replacement selects the protector's existing report path for a verified trigger. */
static const Site sites[] = {
    /* The watchdog otherwise sends SIGKILL to its parent before reporting. */
    {0x1f3b8u, 0x37300248u, 0x14000012u},
    {0x1f408u, 0x373003c8u, 0x1400001eu},
    {0x33b34u, 0x37300428u, 0x14000021u},
    {0x33d9cu, 0x37305d68u, 0x140002ebu},
    {0x3a95cu, 0x37380428u, 0x14000021u},
    {0x51d80u, 0x37385268u, 0x14000293u},
    {0x51fe4u, 0x373839a8u, 0x140001cdu},
    {0x526a0u, 0x37380688u, 0x14000034u},
    {0x57c9cu, 0x37380509u, 0x14000028u},
};
static int armed;
static int applied;

static int protection(uptr address) {
    NativeFile *maps = fopen("/proc/self/maps", "r");
    if (!maps) return -1;
    char line[1024], flags[5];
    uptr start, end;
    int result = -1;
    while (fgets(line, sizeof(line), maps)) {
        if (sscanf(line, "%lx-%lx %4s", &start, &end, flags) == 3
                && address >= start && address < end) {
            result = (flags[0] == 'r' ? 1 : 0) | (flags[1] == 'w' ? 2 : 0)
                    | (flags[2] == 'x' ? 4 : 0);
            break;
        }
    }
    fclose(maps);
    return result;
}

static void flush_instruction(uptr address) {
    __asm__ volatile("dc cvau, %0\n\tdsb ish\n\tic ivau, %0\n\tdsb ish\n\tisb"
                     : : "r"(address) : "memory");
}

static void on_library_loaded(const char *name, void *handle) {
    if (!__atomic_load_n(&armed, __ATOMIC_ACQUIRE) || applied || !name || !handle) return;
    const char *wanted = "libDexHelper.so";
    usize length = strlen(name), suffix = strlen(wanted);
    if (length < suffix || strcmp(name + length - suffix, wanted)) return;
    void *on_load = dlsym(handle, "JNI_OnLoad");
    DlInfo info;
    if (!on_load || !dladdr(on_load, &info) || !info.base) {
        LOG("library identification failed; no changes");
        return;
    }
    uptr base = (uptr)info.base;
    if ((uptr)on_load - base != 0x14798u) {
        LOG("JNI entry mismatch; no changes");
        return;
    }
    for (usize i = 0; i < COUNT(sites); ++i) {
        if (*(volatile u32 *)(base + sites[i].offset) != sites[i].original) {
            LOG("instruction mismatch at 0x%lx; no changes", sites[i].offset);
            return;
        }
    }
    int page_size = getpagesize();
    if (page_size <= 0 || (page_size & (page_size - 1))) return;
    uptr pages[COUNT(sites)];
    int permissions[COUNT(sites)];
    usize count = 0;
    for (usize i = 0; i < COUNT(sites); ++i) {
        uptr page = (base + sites[i].offset) & ~((uptr)page_size - 1);
        int duplicate = 0;
        for (usize j = 0; j < count; ++j) if (pages[j] == page) duplicate = 1;
        if (duplicate) continue;
        int prot = protection(page);
        if (prot < 0 || mprotect((void *)page, page_size, prot | 2)) {
            for (usize j = 0; j < count; ++j)
                mprotect((void *)pages[j], page_size, permissions[j]);
            LOG("could not prepare memory pages; no instructions changed");
            return;
        }
        pages[count] = page;
        permissions[count++] = prot;
    }
    for (usize i = 0; i < COUNT(sites); ++i) {
        uptr address = base + sites[i].offset;
        __atomic_store_n((u32 *)address, sites[i].report_branch, __ATOMIC_RELEASE);
        flush_instruction(address);
    }
    for (usize i = 0; i < count; ++i) {
        if (mprotect((void *)pages[i], page_size, permissions[i]))
            LOG("page permission restoration failed at %lx", pages[i] - base);
    }
    applied = 1;
    LOG("applied %lu verified report branches in app memory", (usize)COUNT(sites));
}

EXPORT void Java_local_shuzi_startupcompat_StartupCompat_armNative(void *env, void *clazz) {
    (void)env; (void)clazz;
    __atomic_store_n(&armed, 1, __ATOMIC_RELEASE);
    LOG("native callback armed");
}

EXPORT LibraryCallback native_init(const NativeApi *api) {
    LOG("native callback registered, API=%u", api ? api->version : 0);
    return on_library_loaded;
}
