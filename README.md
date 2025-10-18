# GccTrace Tool Suite

This repository hosts two complementary tracing toolchains:

- **`cpp-tracer/`** – the original GCC compiler plugin that instruments C/C++ builds and exports execution traces.
- **`python-tracer/`** – a brand-new pure Python tracer that records call graphs, line-by-line execution, and performance metrics for Python programs, including optional Graphviz visualisations.

Both toolchains can be used independently or side-by-side when analysing heterogeneous systems.

---

## Repository layout

```
GccTrace-Tool/
├── README.md
├── CMakeLists.txt            # Entry point that delegates to the C++ tracer build system
├── cpp-tracer/               # GCC plugin sources, headers, docker helpers, unit tests
└── python-tracer/            # Python execution tracer package and CLI
```

### C++ tracer (`cpp-tracer/`)
```
cpp-tracer/
├── CMakeLists.txt            # Builds the gperf GCC plugin
├── include/                  # Shared headers used by the plugin implementation
├── src/                      # Core plugin implementation (plugin.cc, tracking.cc, perf_output.cc)
├── test/                     # Minimal test harness that exercises the plugin
└── docker/                   # Container assets for reproducing the GCC toolchain environment
```

### Python tracer (`python-tracer/`)
```
python-tracer/
├── cli.py                    # Command line interface
└── tracer/                   # Reusable tracing library
    ├── __init__.py
    ├── call_tree.py          # Call tree data structures
    ├── session.py            # Core tracing engine
    └── visualization.py      # ASCII and Graphviz renderers
```

---

## Building and using the C++ GCC tracer

1. **Configure and build**

   ```bash
   cmake -S . -B build
   cmake --build build
   ```

   The shared object `gperf.so` will be generated in the `build/` directory.

2. **Run the bundled test (optional)**

   ```bash
   cmake --build build --target test
   ```

3. **Install the plugin**

   After a successful build you can install the plugin into the GCC plugin directory that CMake detected:

   ```bash
   cmake --install build
   ```

   The plugin accepts the `-fplugin-arg-gperf-trace=<output.json>` argument to control the trace output destination. See the source files in `cpp-tracer/src/` for additional instrumentation details.

---

## Tracing Python programs

### Quick start

```bash
cd python-tracer
python cli.py path/to/script.py -- --script-arg value
```

The tracer will:

- Record the **call trace** for every function under the project root (configurable via `--root`).
- Capture **line-by-line execution** timestamps and optional source code snippets.
- Aggregate **performance statistics** per function (call counts, total time, self time).
- Generate **visualisations**, including an ASCII call tree in the terminal and an optional Graphviz DOT export.

### CLI options

| Option | Description |
| ------ | ----------- |
| `--root <path>` | Restrict tracing to files below the specified directory. Defaults to the traced script directory. |
| `--include-stdlib` | Include calls inside the Python standard library. |
| `--no-source` | Skip capturing source snippets for line events. |
| `--sort-by {total_time,self_time,call_count}` | Choose the metric used to rank the hottest functions. |
| `--top <n>` | Number of rows displayed in the performance summary table. |
| `--max-depth <n>` | Limit the depth of the printed call tree and DOT visualisation. |
| `--max-lines <n>` | Cap how many line execution events are shown in the console. |
| `--dot <path>` | Write a Graphviz DOT call tree that can be rendered with `dot`/Graphviz. |
| `--json <path>` | Export the full trace (calls, lines, stats, call tree) as JSON. |

You can pass additional arguments to the traced script after `--`. For example:

```bash
python cli.py examples/demo.py -- --iterations 10
```

### Programmatic API

The reusable `Tracer` class can be embedded directly inside your tooling:

```python
from tracer import Tracer

tracer = Tracer()
result = tracer.run_script("examples/demo.py")

# Highest-impact functions (sorted by total execution time)
for stats in result.sorted_functions():
    print(stats.function, stats.total_time)

# ASCII call tree
from tracer.visualization import render_ascii_tree
print(render_ascii_tree(result.call_tree))
```

`TraceResult` exposes raw call and line events along with aggregated `FunctionStats`, making it easy to build custom analytics, profilers, or educational visualisations.

---

## Development tips

- The `.gitignore` file excludes CMake build artefacts, Python bytecode, and common virtual environment folders.
- When working on the Python tracer you can install development dependencies locally inside a virtual environment without polluting the repository.
- The Python tracer avoids external dependencies; Graphviz exports are generated as plain DOT files so you can run `dot -Tpng output.dot -o call-tree.png` if you want rendered diagrams.

---

## License

This project follows the licensing terms defined in the repository (see individual files for details).
