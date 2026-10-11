# Tests

Run the commands below from the repository root with Python 3.10+.

Both the regression suite and the official-data checker require a system-installed Lua 5.1 shared library. They fail before running if the library is missing, cannot be loaded or does not provide Lua 5.1. The adapter uses Python's `ctypes` to load the library and verifies `_VERSION`; it does not download or compile a temporary library.

On Debian or Ubuntu, install the test dependencies with:

```sh
sudo apt-get update
sudo apt-get install --no-install-recommends -y liblua5.1-0 coreutils
```

GNU `sort` from `coreutils`, named `sort` or `gnusort`, enables the optional randomized segment-order check. Other implementations, such as uutils, are not used as the reference. The reference converts dots to Tab field separators and uses an explicit `-k` range for each field with `-V`. A behavior probe detects older GNU versions that resolve numeric field ties before comparing the next field; their randomized reference excludes zero-leading numeric runs. Fixed cases always verify the intended ordering for zero and zero-padded numbers, as well as parents and children, empty segments and the Bedrock keys with underscores that exposed whole-key suffix sorting.

The HTTP test needs permission to bind a temporary server to `127.0.0.1`. These dependencies are only needed for tests; the generator uses Python's standard library.

## Regression suite

```sh
python3 -m unittest discover -s tests -v
```

Covers CLI behavior, local and HTTP sources, version selection, column order, keys and fallback, blocked strings, metadata, encodings, Lua string round-trips and the fixed output fixtures under `tests/fixtures/`.

The `.lang` converter tests also cover both comment forms, trailing U+0020 and NBSP cleanup with and without `-t`, leading and interior whitespace and backslash preservation, the exact editor mesh-info key's newline rule through JSON and Lua in both modes, file and record precedence, BOMs, strict decoding, STDIN/STDOUT and rare Unicode characters in keys and values through JSON and the system Lua 5.1 runtime. TranslateParser preparation tests check single-digit index adaptation, integer markers, literal floating-point text, percent runs, URL encodings and the key-specific percentage exception. They also verify literal suffixes, retained multi-digit typed forms and intentionally invalid test strings, with prepared JSON values checked through generated Lua. Local game data is not required by the suite.

## Continuous integration

The [GitHub Actions workflow](../.github/workflows/tests.yml) runs the regression suite on every push, using Python 3.10 and the latest stable Python 3 release on Ubuntu 22.04. It installs the system Lua 5.1 library and `coreutils`, then verifies the Lua runtime before running the suite.

## Official data

```sh
python3 tests/check_official_data.py --cache /tmp/nameprovider-reference
```

Downloads `latest`, `1.21.8` and `1.13`, verifies asset hashes, compares auto and manual output with matching metadata, and checks each output value in Lua 5.1 against its source. Languages include Gothic, Arabic-script Malay, Kannada, Lao, Yiddish and other scripts with supplementary or combining characters.

Use `--versions` to select versions or `--manifest` to use a saved manifest. Omit `--cache` to discard downloads after the check. A cache retains its manifest; remove `manifest.json` to refresh the available versions.
