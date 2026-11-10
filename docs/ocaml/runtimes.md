# Runtimes

Each entry in `runtimes:` names a compiler. Runtimes are built with `opam-compiler`, each into its own opam root under `~/.cache/running-ng/opam-roots/` (set `RUNNING_OPAM_ROOTS` to specify where the roots should be located). A `version:` is first resolved to the commit its tag points to, so a runtime can be uniquely identified by its commit SHA.

```yaml
runtimes:
  ocaml-5.4.1:                 # by release tag
    type: OCaml
    version: "5.4.1"
  ocaml-d8bb46c:               # by commit
    type: OCaml
    commit: "d8bb46c39bf5fcafb513a8ba18e667d3f8c2600a"
  ocaml-5.4.1-fp-flambda:      # same source, different configure
    type: OCaml
    version: "5.4.1"
    configure_args: ["--enable-frame-pointers", "--enable-flambda"]
  ocaml-local:                 # a compiler you built yourself
    type: OCaml
    executable: "/path/to/bin/ocaml"
```

`repo:` selects a fork (default `https://github.com/ocaml/ocaml.git`) consisting of a GitHub URL which is used by `opam-compiler` when resolving `user/repo:ref`. Use either
`version:` or `commit:` to specify a runtime.

## Opam roots

A runtime's opam root is reused as long as everything that determines its
contents is unchanged: the compiler commit, `configure_args`,
`relocatable`, and the opam-repository commit running-ng pins (`opam_repository:`
overrides it for one runtime). A change to one of these makes the runtime get a new
root. Because each run holds a shared lock on the roots it uses, concurrent runs are safe.

`python3 -m running.opam_roots list` shows the roots and what built each one. Note that roots take about 1 GB each and are never removed automatically. To delete old roots, run
`python3 -m running.opam_roots gc --unused-for X`, which removes the ones unused for X days.

## OxCaml

```yaml
oxcaml-trunk:
  type: OxCaml
  commit: "<sha>"
  configure_args: ["--enable-multidomain", "--enable-poll-insertion", "--enable-stack-checks"]
```

An OxCaml runtime gets its own opam root. The compiler is built by
`opam-compiler create oxcaml/oxcaml:<commit>`, currently using `opam-compiler` from
ocaml-opam/opam-compiler#42 (pinned in the tools switch until it is released).
It installs the dune and menhir that the commit's `oxcaml-dev.opam` requires into
a build switch in the same root, and builds OxCaml with them. The runtime switch
gets only the compiler. The default repo is `https://github.com/oxcaml/oxcaml.git`.

No configure flags are added beyond what the build needs, so OxCaml runtimes set
them in `configure_args`. Without multidomain and poll insertion, multicore
programs fail with `failed to allocate domain`.

The runtime switch has no `+ox` packages, so micro benchmarks whose build
scripts `opam install` packages do not build on OxCaml
(ocaml-bench/micro-benches#22).

## MMTk

`type: OCamlMMTk` runs on [ocaml-mmtk](https://github.com/fplaunchpad/ocaml-mmtk),
OCaml 5.5 with [MMTk](https://www.mmtk.io/) in place of the stock collector. It is
a drop-in: the same launch scripts work unchanged.

```yaml
runtimes:
  ocaml-mmtk:
    type: OCamlMMTk
    commit: "cbc66e3efd8f9200f3e84f791a6b6dfc36efce8c"
    # repo: defaults to fplaunchpad/ocaml-mmtk; set it to build another fork
```

The only extra prerequisite is **Rust/cargo at `~/.cargo`**: MMTk's static library
is built by cargo inside the compiler's `make`. Everything else is automatic (ASLR
disabled for every MMTk command, a fixed build-time heap, a `LIBRARY_PATH` that
lets dune-configurator probes link `-lmmtk_ocaml`, and a temporarily relaxed opam
sandbox so cargo can fetch crates). 

Plan and heap are run-time environment variables, supplied as modifiers:

| Env var | Meaning |
|---|---|
| `MMTK_PLAN` | `Immix` (default) · `StickyImmix` · `GenImmix` · `MarkSweep` · `NoGC`. **Native code needs an Immix-family plan.** |
| `MMTK_HEAP_SIZE_MB` | **Fixed** heap size (a hard bound, unlike stock OCaml's soft target) |
| `MMTK_THREADS` | GC worker threads |
| `MMTK_VERBOSE` | print `[mmtk]` init line and exit-time GC stats |

`macro_base.yml` ships `plan` and `threads` as name-value modifiers, so
`|plan-StickyImmix|threads-4` both sets the variables and records them as distinct
dimensions in the contract:

```bash
RUNNING_MACRO_BENCH_DIR=~/macro-benches \
CONFIG_FILE=src/running/config/experiments/mmtk_macro.yml \
  bash run_ocaml_bench_gc_sweep.sh
```

Because `MMTK_HEAP_SIZE_MB` is a hard bound, the `minheap` subcommand can
binary-search the smallest heap each benchmark completes in; MMTk is the only
runtime that supports it.
