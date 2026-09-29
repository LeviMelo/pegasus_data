## ADR-0074: The native DBC engine builds into a per-user cache, never the package; wheels should ship it compiled

**Date:** 2026-09-28. **Status:** active. **Amends:** ADR-0059 (the
first-party DCL decompressor).

**Context.** `decode/_native` compiled `pegasus_blast.c` on first use:
- It looked for `cl.exe` at one hardcoded path, `C:\Program Files\Microsoft
  Visual Studio\2022\Community\SDK\ScopeCppSDK\vc15`, then on PATH.
- It wrote `pegasus_blast.dll`, `.obj`, `.lib` and `.exp` beside the source,
  inside the installed package. A read-only site-packages cannot take them,
  and in the repository they sat in the source tree.
- Measured 2026-09-28 on an 8.2 MB `.dbc` (73.9 MB inflated): the native
  engine takes **0.95 s** and the Python fallback **19.1 s** (20×), with
  byte-identical output. So a user without a compiler, which is most Windows
  users, silently gets a twentyfold slower decode of every file.
- Here, vswhere reports Visual Studio 2019 BuildTools and 2022 Community
  without the C++ toolset, so setuptools cannot build an extension. Only the
  ScopeCppSDK `cl.exe` works.

**Decision.**
- The library is built once into a per-user cache: `%LOCALAPPDATA%\pegasus_data\native`,
  or `$XDG_CACHE_HOME`/`~/.cache/pegasus_data/native`, or `PEGASUS_NATIVE_CACHE`.
  It is named by the source's hash, the platform and the word size, and
  written atomically. Nothing is written into the package.
- Compilers are discovered, not assumed: every Visual Studio install vswhere
  reports (its ScopeCppSDK), `cl.exe` on PATH, and `cc`/`gcc`/`clang`.
- When none builds, the Python engine runs and says so once, with the
  measured cost, instead of silently.
- **Pending the user's decision on publishing:** ship the engine compiled in
  platform wheels built by CI, so that no user needs a compiler. That means a
  small CPython module wrapper and cibuildwheel in the publish workflow
  (STATUS).

**What would reverse it.** A published build that ships the compiled engine
makes the runtime build a fallback for source installs only, and the cache
logic can then shrink to loading.
