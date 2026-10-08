#!/usr/bin/env python3
"""Generate Java Edition NameProvider Lua data using only the standard library."""

import argparse
import codecs
from dataclasses import dataclass
from itertools import zip_longest
import json
import math
from pathlib import Path
import re
import shutil
import sys
import tempfile
import textwrap
from urllib.error import URLError
from urllib.parse import unquote, urljoin, urlparse
from urllib.request import Request, urlopen
from zipfile import BadZipFile, ZipFile


DEFAULT_MANIFEST = "https://piston-meta.mojang.com/mc/game/version_manifest.json"
DEFAULT_ASSETS = "https://resources.download.minecraft.net/"
LANGUAGE_PATTERN = re.compile(r"[a-z0-9_]+\Z")
SUFFIX_PATTERN = re.compile(r"(?:\.[A-Za-z~][A-Za-z0-9~]*)+$")
VERSION_TOKENS = re.compile(r"[0-9]+|[^0-9]")


class GeneratorError(Exception):
    """An input cannot be used to generate the requested table."""


def token_order(text):
    tokens = []
    for part in VERSION_TOKENS.findall(text):
        if "0" <= part[0] <= "9":
            tokens.append((0, part.lstrip("0")))
        elif part == "~":
            tokens.append((-2, ""))
        elif "A" <= part <= "Z" or "a" <= part <= "z":
            tokens.append((ord(part), ""))
        else:
            tokens.append((ord(part) + 256, ""))
    return tokens


def compare_tokens(left, right):
    for a, b in zip_longest(left, right, fillvalue=(-1, "")):
        if a[0] in (-1, 0) and b[0] in (-1, 0):
            # Numeric runs compare by value; zero also equals an absent run.
            a_number = (len(a[1]), a[1])
            b_number = (len(b[1]), b[1])
            if a_number != b_number:
                return -1 if a_number < b_number else 1
        elif a[0] != b[0]:
            return -1 if a[0] < b[0] else 1
    return 0


class VersionKey:
    """The version ordering of `sort -V`, including suffixes and byte ties."""

    def __init__(self, text):
        self.text = text
        self.category = {"": 0, ".": 1, "..": 2}.get(text, 3 if text.startswith(".") else 4)
        suffix = SUFFIX_PATTERN.search(text, 1)
        self.full = token_order(text)
        self.prefix = token_order(text[:suffix.start()]) if suffix else self.full

    def __lt__(self, other):
        if self.category != other.category:
            return self.category < other.category
        comparison = compare_tokens(self.prefix, other.prefix) or compare_tokens(self.full, other.full)
        return comparison < 0 if comparison else self.text < other.text


def language_code(value):
    value = value.lower()
    if not LANGUAGE_PATTERN.fullmatch(value):
        raise GeneratorError(f"invalid language code: {value!r}")
    return value


def language_order(values):
    if not values:
        raise GeneratorError("auto mode requires at least one LANGUAGE unless --list-versions is used")
    languages = [language_code(value) for value in values]
    if len(set(languages)) != len(languages):
        raise GeneratorError("language codes must not be repeated")
    return languages


def parse_json(data, source, encoding=None):
    try:
        # json.loads(bytes) detects UTF-8/16/32, including their BOMs.
        value = json.loads(data.decode(encoding) if encoding else data)
    except (UnicodeError, ValueError, LookupError) as error:
        raise GeneratorError(f"cannot decode JSON from {source}: {error}") from error
    if not isinstance(value, dict):
        raise GeneratorError(f"{source}: expected a JSON object")
    return value


def language_data(data, source, encoding=None):
    translations = parse_json(data, source, encoding)
    for key, value in translations.items():
        if not isinstance(value, str):
            raise GeneratorError(f"{source}: translation {key!r} must be a string")
        try:
            key.encode("utf-8")
            value.encode("utf-8")
        except UnicodeError as error:
            raise GeneratorError(f"{source}: translation {key!r} contains an unpaired Unicode surrogate") from error
    return translations


def resolve_source(source, parent=None):
    parsed = urlparse(source)
    if parsed.scheme in ("http", "https"):
        return source
    if parsed.scheme == "file":
        if parsed.netloc not in ("", "localhost"):
            raise GeneratorError("file URLs must refer to local files")
        return str(Path(unquote(parsed.path)).resolve())
    if parsed.scheme:
        raise GeneratorError(f"unsupported source scheme: {parsed.scheme}")
    if parent and urlparse(parent).scheme in ("http", "https"):
        return urljoin(parent, source)
    path = Path(source).expanduser()
    if parent and not path.is_absolute():
        path = Path(parent).parent / path
    return str(path.resolve())


class Downloader:
    def __init__(self, timeout):
        self.timeout = timeout

    def open(self, source):
        if urlparse(source).scheme in ("http", "https"):
            request = Request(source, headers={"User-Agent": "NameProvider-Data-Generator/Python"})
            return urlopen(request, timeout=self.timeout)
        return Path(source).open("rb")

    def read(self, source):
        with self.open(source) as stream:
            return stream.read()

    def json(self, source):
        return parse_json(self.read(source), source)

    def save(self, source, destination):
        with self.open(source) as stream, destination.open("wb") as target:
            shutil.copyfileobj(stream, target)


@dataclass
class Metadata:
    version: str | None = None
    asset: str | None = None
    asset_note: str | None = None
    version_note: str | None = None


def required_string(mapping, key, context):
    value = mapping.get(key)
    if not isinstance(value, str) or not value:
        raise GeneratorError(f"{context}: missing or invalid {key!r}")
    return value


def load_manifest(arguments):
    downloader = Downloader(arguments.timeout)
    manifest_source = resolve_source(arguments.manifest)
    manifest = downloader.json(manifest_source)
    versions = manifest.get("versions")
    if not isinstance(versions, list) or not versions or not all(isinstance(v, dict) for v in versions):
        raise GeneratorError("manifest must contain a non-empty 'versions' list")
    return downloader, manifest_source, manifest


def available_versions(arguments):
    _, _, manifest = load_manifest(arguments)
    rows = [("VERSION", "TYPE", "RELEASE_TIME")]
    for entry in manifest["versions"]:
        fields = (required_string(entry, "id", "manifest version"), entry.get("type", ""), entry.get("releaseTime", entry.get("time", "")))
        if any(not isinstance(field, str) or any(char in field for char in "\t\r\n") for field in fields):
            raise GeneratorError("version list fields must be strings without tabs or line breaks")
        rows.append(fields)
    widths = [max(len(value) for value in column) for column in zip(*rows)]
    lines = ["  ".join(value.ljust(width) for value, width in zip(row, widths)).rstrip() for row in rows]
    lines.insert(1, "  ".join("-" * width for width in widths))
    return "\n".join(lines) + "\n"


def automatic_data(arguments):
    languages = language_order(arguments.languages)
    downloader, manifest_source, manifest = load_manifest(arguments)
    versions = manifest["versions"]
    requested = arguments.version
    if requested in ("latest-release", "latest-snapshot"):
        latest = manifest.get("latest", {})
        if not isinstance(latest, dict):
            raise GeneratorError("manifest 'latest' must be an object")
        requested = required_string(latest, requested.removeprefix("latest-"), "manifest latest")
    entry = versions[0] if requested == "latest" else next((v for v in versions if v.get("id") == requested), None)
    if entry is None:
        raise GeneratorError(f"version {requested!r} is not in the manifest")
    version_id = required_string(entry, "id", "manifest version")
    version_source = resolve_source(required_string(entry, "url", "manifest version"), manifest_source)
    version = downloader.json(version_source)
    asset_index = version.get("assetIndex")
    if not isinstance(asset_index, dict):
        raise GeneratorError(f"{version_id}: no asset index (JSON languages require Java Edition 1.13 or later)")
    asset_url = required_string(asset_index, "url", "asset index")
    assets = downloader.json(resolve_source(asset_url, version_source))
    objects = assets.get("objects")
    if not isinstance(objects, dict):
        raise GeneratorError("asset index must contain an 'objects' object")
    for language in languages:
        if language != "en_us" and f"minecraft/lang/{language}.json" not in objects:
            raise GeneratorError(f"{version_id}: language {language!r} has no JSON asset")

    data = {}
    if "en_us" in languages:
        downloads = version.get("downloads", {})
        client = downloads.get("client", {}) if isinstance(downloads, dict) else {}
        if not isinstance(client, dict):
            raise GeneratorError("version metadata has no client download")
        client_source = resolve_source(required_string(client, "url", "client download"), version_source)
        with tempfile.TemporaryDirectory(prefix="nameprovider-") as temporary:
            client_path = Path(temporary) / "client.jar"
            downloader.save(client_source, client_path)
            with ZipFile(client_path) as archive:
                try:
                    english = archive.read("assets/minecraft/lang/en_us.json")
                except KeyError as error:
                    raise GeneratorError(f"{version_id}: client has no en_us.json (requires Java Edition 1.13 or later)") from error
        data["en_us"] = language_data(english, f"{version_id} client en_us.json", arguments.encoding)
    asset_base = resolve_source(arguments.assets_base)
    for language in languages:
        if language == "en_us":
            continue
        asset = objects[f"minecraft/lang/{language}.json"]
        if not isinstance(asset, dict):
            raise GeneratorError(f"invalid asset entry for {language}")
        digest = required_string(asset, "hash", f"{language} asset")
        if not re.fullmatch(r"[0-9a-f]{40}", digest):
            raise GeneratorError(f"invalid SHA-1 hash for {language}")
        resource = f"{digest[:2]}/{digest}"
        if urlparse(asset_base).scheme in ("http", "https"):
            source = urljoin(asset_base.rstrip("/") + "/", resource)
        else:
            source = str(Path(asset_base) / resource)
        data[language] = language_data(downloader.read(source), source, arguments.encoding)
    time = entry.get("time", entry.get("releaseTime", ""))
    if not isinstance(time, str):
        raise GeneratorError("manifest version time must be a string")
    return data[languages[0]], [data[language] for language in languages], Metadata(version_id, asset_url, time)


def manual_data(arguments):
    files = [Path(filename).expanduser() for filename in arguments.files]
    columns = [language_data(path.read_bytes(), path, arguments.encoding) for path in files]
    metadata = None
    if any(value is not None for value in (arguments.version, arguments.asset, arguments.asset_note, arguments.version_note)):
        metadata = Metadata(arguments.version, arguments.asset, arguments.asset_note, arguments.version_note)
    return columns[0], columns, metadata


def lua_string(value, quote='"'):
    escapes = {"\\": "\\\\", quote: "\\" + quote, "\b": "\\b", "\f": "\\f", "\n": "\\n", "\r": "\\r", "\t": "\\t"}
    return quote + "".join(escapes.get(char, f"\\{ord(char):03d}" if ord(char) < 32 else char) for char in value) + quote


def read_blocked_strings(arguments):
    keys = arguments.blocked_strings.split(",") if arguments.blocked_strings is not None else []
    if arguments.blocked_strings_file is not None:
        source = arguments.blocked_strings_file
        data = sys.stdin.buffer.read() if source == "-" else Path(source).expanduser().read_bytes()
        if data.startswith((codecs.BOM_UTF32_BE, codecs.BOM_UTF32_LE)):
            encoding = "utf-32"
        elif data.startswith((codecs.BOM_UTF16_BE, codecs.BOM_UTF16_LE)):
            encoding = "utf-16"
        else:
            encoding = "utf-8-sig"
        text = data.decode(encoding)
        keys.extend(line.removesuffix("\r") for line in text.split("\n"))
    return {key for key in keys if key}


def blocked_strings_comment(keys):
    lines = ["BLOCKED STRINGS"]
    for key in keys:
        lines.append("\t" + "".join(f"\\{ord(char):03d}" if ord(char) < 32 else char for char in key))
    contents = "\n".join(lines)
    equals = ""
    while f"]{equals}]" in contents:
        equals += "="
    return f"--[{equals}[\n{contents}\n]{equals}]"


def render(base, columns, metadata=None, blocked_strings=()):
    lines = []
    if metadata:
        for value in (metadata.version, metadata.asset, metadata.asset_note, metadata.version_note):
            if value is not None and ("\n" in value or "\r" in value):
                raise GeneratorError("metadata must not contain line breaks")
        if metadata.version_note is not None and metadata.version is None:
            raise GeneratorError("--version-note requires --version")
        if metadata.asset_note is not None and metadata.asset is None:
            raise GeneratorError("--asset-note requires --asset")
        if metadata.version is not None:
            note = f" ({metadata.version_note})" if metadata.version_note is not None else ""
            lines.append(f"-- version: {metadata.version}{note}")
        if metadata.asset is not None:
            note = f" ({metadata.asset_note})" if metadata.asset_note is not None else ""
            lines.append(f"-- asset: {metadata.asset}{note}")
    keys = sorted(base, key=VersionKey)
    blocked = set(blocked_strings)
    matched = sorted(blocked.intersection(base))
    if matched:
        lines.append(blocked_strings_comment(matched))
    lines.append("return {")
    if metadata and metadata.version is not None:
        lines.append(f"\t[ '_meta.version' ] = {lua_string(metadata.version)},")
    for key in keys:
        translations = ", ".join(lua_string(base[key] if key in blocked else column.get(key, base[key])) for column in columns)
        lines.append(f"\t[ {lua_string(key, chr(39))} ] = {{ {translations} }},")
    lines.append("}")
    return "\n".join(lines) + "\n"


def positive_timeout(value):
    try:
        timeout = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("timeout must be a positive number") from error
    if not math.isfinite(timeout) or timeout <= 0:
        raise argparse.ArgumentTypeError("timeout must be a positive finite number")
    return timeout


def input_encoding(value):
    try:
        codecs.lookup(value)
    except LookupError as error:
        raise argparse.ArgumentTypeError(f"unknown encoding: {value}") from error
    return value


class HelpFormatter(argparse.HelpFormatter):
    def _split_lines(self, text, width):
        return textwrap.wrap(" ".join(text.split()), width, break_long_words=False, break_on_hyphens=False)


def add_global_options(parser, defaults=True):
    options = parser.add_argument_group("global options")
    options.add_argument("-h", "--help", action="help", help="show this help message and exit")
    options.add_argument("-e", "--encoding", type=input_encoding, default=None if defaults else argparse.SUPPRESS, help="language JSON input encoding; otherwise detect UTF-8/16/32 with or without BOM")
    options.add_argument("-o", "--output", default="-" if defaults else argparse.SUPPRESS, help="UTF-8 output path; - means STDOUT (default: STDOUT)")
    options.add_argument("-b", "--blocked-strings", metavar="KEYS", default=None if defaults else argparse.SUPPRESS, help="comma-separated exact keys whose later columns must use the first language")
    options.add_argument("-B", "--blocked-strings-file", metavar="FILE", default=None if defaults else argparse.SUPPRESS, help="one exact key per line from a UTF-8 or BOM-marked UTF-16/32 file; - reads STDIN")


def make_parser():
    parser = argparse.ArgumentParser(description=__doc__, add_help=False, formatter_class=HelpFormatter, epilog="Without a subcommand, only this help is shown; no data is downloaded or written.")
    add_global_options(parser)
    subparsers = parser.add_subparsers(dest="mode")
    auto = subparsers.add_parser("auto", add_help=False, formatter_class=HelpFormatter, help="download a Minecraft version and its language data")
    add_global_options(auto, defaults=False)
    auto.add_argument("-l", "--list-versions", action="store_true", help="list manifest version IDs, types and release times without downloading game data")
    auto.add_argument("-v", "--version", default="latest", help="version ID, latest (first manifest entry), latest-release, or latest-snapshot")
    auto.add_argument("--manifest", default=DEFAULT_MANIFEST, help="manifest HTTP(S) URL or local JSON file (default: %(default)s)")
    auto.add_argument("--assets-base", default=DEFAULT_ASSETS, help="language asset HTTP(S) base URL or local object directory (default: %(default)s)")
    auto.add_argument("--timeout", type=positive_timeout, default=30, help="network timeout in seconds (default: 30)")
    manual = subparsers.add_parser("manual", add_help=False, formatter_class=HelpFormatter, help="use local language JSON files")
    add_global_options(manual, defaults=False)
    manual.add_argument("-v", "--version", help="version text for _meta.version and the version comment")
    manual.add_argument("--version-note", help="annotation in parentheses after the version comment; requires --version")
    manual.add_argument("--asset", help="asset source text for the asset comment")
    manual.add_argument("--asset-note", help="annotation in parentheses after the asset comment; requires --asset")
    auto.add_argument("languages", nargs="*", metavar="LANGUAGE", help="language codes in output column order, required unless listing versions; first language supplies keys and fallback")
    manual.add_argument("files", nargs="+", metavar="JSON", help="language JSON files in output column order; first file supplies keys and fallback")
    return parser


def write_output(contents, output):
    encoded = contents.encode("utf-8")
    if output == "-":
        sys.stdout.buffer.write(encoded)
        sys.stdout.buffer.flush()
    else:
        Path(output).write_bytes(encoded)


def main(argv=None):
    parser = make_parser()
    arguments = parser.parse_args(argv)
    if arguments.mode is None:
        parser.print_help()
        return 0
    try:
        if arguments.mode == "auto" and arguments.list_versions:
            contents = available_versions(arguments)
        else:
            if arguments.mode == "auto":
                language_order(arguments.languages)
            blocked = read_blocked_strings(arguments)
            base, columns, metadata = automatic_data(arguments) if arguments.mode == "auto" else manual_data(arguments)
            contents = render(base, columns, metadata, blocked)
        write_output(contents, arguments.output)
    except (GeneratorError, OSError, URLError, BadZipFile, UnicodeError) as error:
        parser.error(str(error))
    except KeyboardInterrupt:
        print("Generation cancelled.", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
