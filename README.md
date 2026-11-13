# carton-purifier

Locked, Nix-resolved CPAN dependencies for Carton and Perl.

## Quickstart

From a project with `cpanfile`:

```sh
nix shell 'github:nix-purifiers/carton-purifier'
carton-purifier lock
carton install
carton exec prove -lr t
```

The wrappers activate an immutable Perl library environment. Without a companion
lockfile, they warn and run ordinary tools with impure resolution. You can also
install the wrappers using your normal installation method.

Commit `cpanfile.snapshot` and `carton-purifier.lock.json`. Native Carton selects
the distributions; the companion records their archive hashes, prerequisites,
inputs and SDK. `carton install` prepares the Nix environment automatically.
`carton-purifier prefetch` prepares it explicitly.

CPAN can discover prerequisites during configuration and XS compilation.
Locking uses a temporary native installation to capture that metadata. Those
installation outputs are discarded; Nix builds the delivered libraries from
the recorded archives.

## Updates and project sessions

```sh
carton-purifier lock --update
carton install
```

Updates use native Carton. Application edits reuse the dependency environment;
changes to `cpanfile`, the snapshot or the SDK require locking again.

Declare additional text files read by `cpanfile`:

```sh
carton-purifier lock --input deps.pl
```

Relocking retains these input declarations. Files must be within the project.

Nix producers can also supply installed Perl libraries through their
`projections.perl` projection:

```sh
carton-purifier lock --dependency .#myNativeLibrary
carton-purifier prefetch
```

Repeat `--dependency` for additional Nix flake outputs. Commit the generated
`.carton-purifier-dependencies.json` alongside both lockfiles. Its sorted,
unique locators are authored lock inputs; subsequent commands resolve those
outputs and verify their original producer identities, catalogs and bytes.
Relative paths resolve from the project directory. Missing or foreign
projections fail instead of falling back to CPAN.

Produced libraries and modules already in the selected Perl SDK satisfy native
Carton requirements without becoming CPAN distributions. Their native versions,
runtime requirements and loader paths are checked against that SDK. CPAN
modules and XS libraries cannot shadow their owned lookup paths. Use
`--without GROUP` during capture to retain a native Carton group selection;
relocking preserves it unless another selection is supplied.

```sh
carton-purifier shell
prove -lr t
perl -Ilib bin/example
```

The project shell provides the library environment to child commands. Ordinary
`local/` modules cannot override the prepared libraries. Session state and GC
roots live in `.carton-purifier/`; ignore it, `local/`, `blib/` and generated
`vendor/cache/` files in Git.

`carton bundle` exports the pinned source archives to the normal `vendor/cache`
location. Use the helper to update package selections; the prepared library prefix is
immutable.

## Editors

The supplied PerlNavigator wrapper uses the locked Perl environment:

```sh
perlnavigator --stdio
```

Dependency definitions resolve into the Nix library prefix. The shell also
provides `perl`, `prove` and `perldoc`.

## Build the project in Nix

Optionally use the overlay's builder:

```nix
pkgs.carton-purifier.buildCartonProject {
  src = ./.;
}
```

It returns `packages.environment`, `packages.project`, `packages.default`,
`tests`, `release` and `fetches`. Output names are known during evaluation.
The default builds, tests and installs MakeMaker or Module::Build projects.
`fetchers`, `nativeBuildInputs`, `doCheck`, `buildCommand`, `checkCommand`,
`installCommand` and `srcFilter` customize it. Installed scripts retain the
prepared libraries. Source releases include both lockfiles.

For a lock captured with Nix dependencies, pass the same original producers:

```nix
pkgs.carton-purifier.buildCartonProject {
  src = ./.;
  dependencies = [ myNativeLibrary ];
  without = [ ];
}
```

Use the same owning Carton scope and Perl SDK for capture and building. A
custom scope can select `perl = applicationPerl` through `overrideScope`; the
builder retains that original interpreter, SDK modules and compiler inputs.
Producer projections retain their original outputs and native MakeMaker
observations, including XS libraries, rather than repackaging them as CPAN
archives. Capture and replay reject a changed SDK, provider or native graph.

```sh
carton-purifier publish \
  --repo OWNER/REPO \
  --tag vVERSION
```

## Current scope

Carton 1.0.35 and Perl 5.42.3 on Linux x86_64 and aarch64. Public CPAN archive
distributions, test-group dependencies, pure Perl and XS modules are supported.
Git sources and private providers need additional capture adapters. XS packages
requiring extra system libraries need a customized SDK. The installed native
graph must match the capture; missing prerequisites fail inside the sandbox.

## Credits

The purifier idea was inspired by nixcloud's
[cargo (libnix)](https://github.com/nixcloud/cargo).
