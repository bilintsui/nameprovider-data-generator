# Tests

Run the commands below from the repository root with Python 3.10+.

Both the regression suite and the official-data checker require a system-installed Lua 5.1 shared library. They fail before running if the library is missing, cannot be loaded or does not provide Lua 5.1. The adapter uses Python's `ctypes` to load the library and verifies `_VERSION`; it does not download or compile a temporary library.

On Debian or Ubuntu, install the test dependencies with:

```sh
sudo apt-get update
sudo apt-get install --no-install-recommends -y liblua5.1-0 coreutils
```

GNU `sort` from `coreutils`, named `sort` or `gnusort`, enables the optional randomized segment-order check. The reference compares dot-separated key segments using Tab field separators and explicit `-k` ranges with `-V`. Fixed cases cover parents and children, empty segments, zero and zero-padded numbers, and keys containing underscores.

The HTTP test needs permission to bind a temporary server to `127.0.0.1`. These dependencies are only needed for tests; the generator uses Python's standard library.

## Regression suite

```sh
python3 -m unittest discover -s tests -v
```

Covers CLI behavior, local and HTTP sources, version selection, column order, keys and fallback, blocked strings, metadata, encodings, Lua string round-trips and the fixed output fixtures under `tests/fixtures/`.

The `.lang` converter tests also cover both comment forms, trailing U+0020 and NBSP cleanup with and without `-t`, leading and interior whitespace and backslash preservation, line-break preservation through JSON and Lua in both modes, file and record precedence, BOMs, strict decoding, STDIN/STDOUT and rare Unicode characters in keys and values through JSON and the system Lua 5.1 runtime. TranslateParser preparation tests check single-digit index adaptation, integer markers, literal floating-point text, percent runs and URL encodings. They also verify literal suffixes and retained multi-digit typed forms, with prepared JSON values checked through generated Lua. Local game data is not required by the suite.

## Continuous integration

The [GitHub Actions workflow](../.github/workflows/tests.yml) runs the regression suite on every push, using Python 3.10 and the latest stable Python 3 release on Ubuntu 22.04. It installs the system Lua 5.1 library and `coreutils`, then verifies the Lua runtime before running the suite.

## Official data

```sh
python3 tests/check_official_data.py --cache /tmp/nameprovider-reference
```

Downloads `latest`, `1.21.8` and `1.13`, verifies asset hashes, compares auto and manual output with matching metadata, and checks each output value in Lua 5.1 against its source. Languages include Gothic, Arabic-script Malay, Kannada, Lao, Yiddish and other scripts with supplementary or combining characters.

Use `--versions` to select versions or `--manifest` to use a saved manifest. Omit `--cache` to discard downloads after the check. A cache retains its manifest; remove `manifest.json` to refresh the available versions.
