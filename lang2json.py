#!/usr/bin/env python3
"""Convert and merge selected Bedrock .lang files into a language JSON object."""

import argparse
import codecs
import json
from pathlib import Path
import re
import sys


URL_PATTERN = re.compile(r"\b[A-Za-z][A-Za-z0-9+.-]*://[^\s<>\"']+")
INDEXED_PATTERN = re.compile(r"%([0-9]+)\$([sd])")
URL_ESCAPE_PATTERN = re.compile(r"%[0-9A-Fa-f]{2}")
# Confirmed literal percentage, scoped to its key and bare source shape.
# Do not infer the locale from the filename or classify every %100 as text.
LITERAL_PERCENT_EXCEPTIONS = {
    "options.languageWarning": re.compile(r"(?<!%)%100(?![0-9A-Za-z$])"),
}
# These editor strings use backslash-n as a line break in the Wiki data.
# Other keys retain their literal backslashes, including paths and key labels.
NEWLINE_KEYS = {"resourcePack.editor.customMeshTool.label.meshInfoValue"}


class ConversionError(ValueError):
    """An input cannot be converted without losing data."""


def input_encoding(value):
    try:
        codecs.lookup(value)
    except LookupError as error:
        raise argparse.ArgumentTypeError(f"unknown encoding: {value}") from error
    return value


def decode_input(data, source, encoding=None):
    if encoding is None:
        if data.startswith((codecs.BOM_UTF32_LE, codecs.BOM_UTF32_BE)):
            encoding = "utf-32"
        elif data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
            encoding = "utf-16"
        else:
            encoding = "utf-8-sig"
    try:
        text = data.decode(encoding)
        # These codecs already consume the BOM; a second U+FEFF is data.
        if codecs.lookup(encoding).name not in {"utf-8-sig", "utf-16", "utf-32"}:
            text = text.removeprefix("\ufeff")
        return text
    except (UnicodeError, LookupError) as error:
        raise ConversionError(f"{source}: cannot decode input as {encoding}: {error}") from error


def parse_lang(data, source, encoding=None):
    records = {}
    # splitlines() would also split Unicode separators that belong to the text.
    for number, line in enumerate(decode_input(data, source, encoding).split("\n"), 1):
        line = line.removesuffix("\r")
        if not line.strip() or line.lstrip(" \t").startswith("#"):
            continue
        comments = [position for marker in ("##", "\t#") if (position := line.find(marker)) >= 0]
        if comments:
            # Tabs separate comments from the translation.
            line = line[:min(comments)].rstrip("\t")
        key, separator, value = line.partition("=")
        if not separator:
            raise ConversionError(f"{source}:{number}: expected KEY=VALUE")
        if not key:
            raise ConversionError(f"{source}:{number}: empty key")
        # Remove trailing padding without stripping leading or interior whitespace.
        value = value.rstrip(" \u00a0")
        if key in NEWLINE_KEYS:
            value = value.replace(r"\n", "\n")
        records[key] = value
    return records


def translate_parser_string(key, value):
    """Prepare original Bedrock text once, without rescanning generated syntax."""
    if "%" not in value or key.startswith("translation.test.invalid"):
        return value
    urls = [(match.start(), match.end()) for match in URL_PATTERN.finditer(value)]
    literal_percent = LITERAL_PERCENT_EXCEPTIONS.get(key)
    parts = []
    cursor = 0
    while (position := value.find("%", cursor)) >= 0:
        parts.append(value[cursor:position])
        if (match := INDEXED_PATTERN.match(value, position)):
            # Keep multi-digit typed forms intact; single-digit integers become strings.
            parts.append(f"%{match.group(1)}$s" if len(match.group(1)) == 1 else match.group())
            cursor = match.end()
        elif value.startswith(("%s", "%d"), position):
            parts.append("%s")
            cursor = position + 2
        elif literal_percent is not None and literal_percent.match(value, position):
            parts.append("%%")
            cursor = position + 1
        elif any(start <= position < end for start, end in urls) and (match := URL_ESCAPE_PATTERN.match(value, position)):
            # URL percent encodings are text, even when they look like %N.
            parts.append("%" + match.group())
            cursor = match.end()
        elif position + 1 < len(value) and "0" <= value[position + 1] <= "9":
            # Only one ASCII digit belongs to a bare index; retain its suffix.
            parts.append(f"%{value[position + 1]}$s")
            cursor = position + 2
        else:
            # Each original literal % needs its own escape, including runs of %.
            parts.append("%%")
            cursor = position + 1
    parts.append(value[cursor:])
    return "".join(parts)


def make_parser():
    parser = argparse.ArgumentParser(description=__doc__, epilog="Without arguments, only help is shown. Trailing spaces (U+0020) and no-break spaces (U+00A0) are removed from values. The editor mesh-info key's backslash-n sequences become newlines; other backslash sequences are preserved. Format characters are preserved unless --translate-parser is selected.")
    parser.add_argument("-e", "--encoding", type=input_encoding, help="input encoding; otherwise use UTF-8 or BOM-marked UTF-16/32")
    parser.add_argument("-o", "--output", default="-", help="UTF-8 JSON output path; - means STDOUT (default: STDOUT)")
    parser.add_argument("-t", "--translate-parser", action="store_true", help="prepare original Bedrock values once for TranslateParser: adapt single-digit indices and integer markers, and escape literal percent signs")
    parser.add_argument("files", nargs="+", metavar="FILE", help="input files from highest to lowest priority; first file wins conflicts, last record within each file wins; - reads STDIN once")
    return parser


def main(argv=None):
    parser = make_parser()
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        parser.print_help()
        return 0
    arguments = parser.parse_intermixed_args(argv)
    try:
        if arguments.files.count("-") > 1:
            raise ConversionError("STDIN (-) can only be read once")
        records = {}
        for filename in arguments.files:
            data = sys.stdin.buffer.read() if filename == "-" else Path(filename).read_bytes()
            for key, value in parse_lang(data, "STDIN" if filename == "-" else filename, arguments.encoding).items():
                records.setdefault(key, value)
        if arguments.translate_parser:
            records = {key: translate_parser_string(key, value) for key, value in records.items()}
        # Validate every input before writing anything, including an existing file.
        output = (json.dumps(records, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        if arguments.output == "-":
            sys.stdout.buffer.write(output)
            sys.stdout.buffer.flush()
        else:
            Path(arguments.output).write_bytes(output)
    except (ConversionError, OSError, UnicodeError) as error:
        parser.error(str(error))
    except KeyboardInterrupt:
        print("Conversion cancelled.", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
