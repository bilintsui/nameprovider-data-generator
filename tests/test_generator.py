import contextlib
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import random
import shutil
import string
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from lua_runtime import LuaTable
from support import ROOT, generator, make_fixture


class GeneratorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with LuaTable(b"return {}"):
            pass

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="nameprovider-test-")
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.files, self.translations, self.urls = make_fixture(self.directory)

    def cli(self, *arguments, input=None):
        return subprocess.run([sys.executable, str(ROOT / "generator.py"), *arguments], cwd=self.directory, input=input, capture_output=True, timeout=20)

    def test_no_arguments_only_print_help(self):
        before = set(self.directory.iterdir())
        with patch.object(generator.Downloader, "open", side_effect=AssertionError("unexpected network access")):
            with contextlib.redirect_stdout(io.StringIO()) as stdout:
                self.assertEqual(generator.main([]), 0)
        self.assertIn("usage:", stdout.getvalue())
        self.assertEqual(set(self.directory.iterdir()), before)
        result = self.cli()
        self.assertEqual(result.returncode, 0)
        self.assertTrue(result.stdout.startswith(b"usage: generator.py [-h] [-e ENCODING] [-o OUTPUT]"))
        self.assertIn(b"global options:", result.stdout)
        for option in (rb"-h, --help", rb"-e(?: ENCODING)?, --encoding ENCODING", rb"-o(?: OUTPUT)?, --output OUTPUT"):
            self.assertRegex(result.stdout, option)
        self.assertFalse((self.directory / "result.lua").exists())

    def test_manual_uses_file_order_and_english_fallback(self):
        result = self.cli("manual", "en_us.json", "zh_tw.json", "zh_cn.json")
        self.assertEqual(result.returncode, 0, result.stderr)
        output = result.stdout
        self.assertIn(b'[ \'item.test2\' ] = { "Two", "\xe8\xb2\xb3", "\xe4\xba\x8c" },', output)
        self.assertIn(b'[ \'item.test10\' ] = { "Ten", "Ten", "\xe5\x8d\x81" },', output)
        self.assertNotIn(b"only.translation", output)
        self.assertNotIn(b"_meta.version", output)
        self.assertLess(output.index(b"item.test2"), output.index(b"item.test10"))
        for language, path in self.files.items():
            self.assertTrue(path.exists(), language)
        self.assertFalse((self.directory / "result.lua").exists())

    def test_manual_uses_first_file_without_inferring_language(self):
        renamed = self.directory / "custom translations.json"
        renamed.write_bytes(self.files["zh_tw"].read_bytes())
        result = self.cli("manual", "-o", "custom.lua", str(renamed), "en_us.json", "zh_hk.json")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, b"")
        output = (self.directory / "custom.lua").read_bytes()
        self.assertNotIn(b"item.test10", output)
        self.assertNotIn(b"only.english", output)
        with LuaTable(output) as table:
            self.assertEqual(table.row("item.test2", 3), ["貳", "Two", "貳"])
            self.assertEqual(table.row("quote.test", 3), ["引號", self.translations["en_us"]["quote.test"], "𥹉"])

    def test_manual_metadata_matches_auto_output(self):
        automatic = self.cli("auto", "--manifest", "manifest.json", "--assets-base", "objects", "en_us", "zh_hk")
        self.assertEqual(automatic.returncode, 0, automatic.stderr)
        for version_option in ("-v", "--version"):
            with self.subTest(version_option=version_option):
                manual = self.cli("manual", version_option, "snapshot-test", "--asset", "assets.json", "--asset-note", "2026-10-06T13:00:46+00:00", "en_us.json", "zh_hk.json")
                self.assertEqual(manual.returncode, 0, manual.stderr)
                self.assertEqual(manual.stdout, automatic.stdout)
                with LuaTable(manual.stdout) as table:
                    self.assertEqual(table.field("_meta.version"), "snapshot-test")
                    self.assertEqual(table.row("quote.test", 2), [self.translations["en_us"]["quote.test"], "𥹉"])

    def test_manual_version_note_is_separate_from_lua_version(self):
        version = 'snapshot-"𐍈\\'
        note = "crowdin-approved+suggested-𥹉-e\u0301"
        result = self.cli("manual", "-v", version, "--version-note", note, "en_us.json")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.startswith(f"-- version: {version} ({note})\nreturn {{\n".encode()))
        self.assertNotIn(b"-- asset:", result.stdout)
        with LuaTable(result.stdout) as table:
            self.assertEqual(table.field("_meta.version"), version)
            self.assertEqual(table.row("quote.test", 1), [self.translations["en_us"]["quote.test"]])

    def test_manual_metadata_fields_can_be_supplied_independently(self):
        cases = (
            (["--version", "latest"], b"-- version: latest\nreturn {\n", "latest"),
            (["--asset", "assets.json"], b"-- asset: assets.json\nreturn {\n", None),
            (["--version", "snapshot-test", "--asset", "assets.json"], b"-- version: snapshot-test\n-- asset: assets.json\nreturn {\n", "snapshot-test"),
        )
        for options, prefix, version in cases:
            with self.subTest(options=options):
                result = self.cli("manual", *options, "zh_tw.json")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertTrue(result.stdout.startswith(prefix))
                if version is None:
                    self.assertNotIn(b"_meta.version", result.stdout)
                with LuaTable(result.stdout) as table:
                    if version is not None:
                        self.assertEqual(table.field("_meta.version"), version)
                    self.assertEqual(table.row("item.test2", 1), ["貳"])

    def test_blocked_strings_force_first_column_in_both_modes_and_positions(self):
        expected_comment = b"--[[\nBLOCKED STRINGS\n\titem.test2\n\tquote.test\n]]\nreturn {\n"
        keys = "quote.test,item.test2,item.test,only.english,missing"
        for command, specific in (
            ("auto", ["--manifest", "manifest.json", "--assets-base", "objects", "lzh", "en_us", "zh_hk"]),
            ("manual", ["lzh.json", "en_us.json", "zh_hk.json"]),
        ):
            for option in ("-b", "--blocked-strings"):
                for before_subcommand in (True, False):
                    with self.subTest(command=command, option=option, before_subcommand=before_subcommand):
                        arguments = [option, keys, command, *specific] if before_subcommand else [command, option, keys, *specific]
                        result = self.cli(*arguments)
                        self.assertEqual(result.returncode, 0, result.stderr)
                        self.assertIn(expected_comment, result.stdout)
                        self.assertNotIn(b"only.english", result.stdout)
                        with LuaTable(result.stdout) as table:
                            self.assertEqual(table.row("item.test2", 3), ["兩", "兩", "兩"])
                            self.assertEqual(table.row("quote.test", 3), ["曰", "曰", "曰"])
                            self.assertEqual(table.row("item.test10", 3), ["拾", "Ten", "拾"])

    def test_blocked_strings_file_and_stdin_match_comma_input(self):
        path = self.directory / "blocked keys.txt"
        text = "\r\nquote.test\r\nitem.test2\r\nquote.test\r\n\r\n"
        for command, specific in (
            ("auto", ["--manifest", "manifest.json", "--assets-base", "objects", "lzh", "en_us", "zh_hk"]),
            ("manual", ["lzh.json", "en_us.json", "zh_hk.json"]),
        ):
            expected = self.cli(command, "-b", "item.test2,quote.test", *specific)
            self.assertEqual(expected.returncode, 0, expected.stderr)
            for encoding in ("utf-8", "utf-8-sig", "utf-16", "utf-32"):
                data = text.encode(encoding)
                path.write_bytes(data)
                for option in ("-B", "--blocked-strings-file"):
                    for source in (str(path), "-"):
                        with self.subTest(command=command, encoding=encoding, option=option, source=source):
                            result = self.cli(option, source, command, *specific, input=data if source == "-" else None)
                            self.assertEqual(result.returncode, 0, result.stderr)
                            self.assertEqual(result.stdout, expected.stdout)

    def test_blocked_sources_are_merged_and_deduplicated(self):
        (self.directory / "blocked.txt").write_text("quote.test\nitem.test2\nquote.test\n", encoding="utf-8")
        expected = self.cli("manual", "-b", "item.test2,quote.test", "en_us.json", "zh_tw.json")
        self.assertEqual(expected.returncode, 0, expected.stderr)
        for before, after in ((["-b", "item.test2,item.test2"], ["-B", "blocked.txt"]), (["-B", "blocked.txt"], ["-b", "item.test2"])):
            with self.subTest(before=before):
                result = self.cli(*before, "manual", *after, "en_us.json", "zh_tw.json")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, expected.stdout)

    def test_blocked_utf8_control_key_in_file_and_stdin(self):
        key = "\x00key"
        for filename, value in (("first.json", "𐍈 first"), ("second.json", "𥹉 second")):
            (self.directory / filename).write_text(json.dumps({key: value}, ensure_ascii=False), encoding="utf-8")
        data = (key + "\n").encode("utf-8")
        path = self.directory / "blocked.txt"
        path.write_bytes(data)
        for source in (str(path), "-"):
            with self.subTest(source=source):
                result = self.cli("manual", "-B", source, "first.json", "second.json", input=data if source == "-" else None)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(b"\t\\000key\n", result.stdout)
                with LuaTable(result.stdout) as table:
                    self.assertEqual(table.row(key, 2), ["𐍈 first", "𐍈 first"])

    def test_blocked_comment_uses_key_name_order_and_rows_keep_version_order(self):
        result = self.cli("manual", "-b", "item.test2,item.test10", "en_us.json", "zh_cn.json")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.startswith(b"--[[\nBLOCKED STRINGS\n\titem.test10\n\titem.test2\n]]\nreturn {\n"))
        rows = result.stdout.split(b"return {\n", 1)[1]
        self.assertLess(rows.index(b"item.test2"), rows.index(b"item.test10"))
        with LuaTable(result.stdout) as table:
            self.assertEqual(table.row("item.test2", 2), ["Two", "Two"])
            self.assertEqual(table.row("item.test10", 2), ["Ten", "Ten"])

    def test_blocked_keys_preserve_unicode_exact_matching_and_lua51_comments(self):
        blocked = ["rare𐍈𥹉", "e\u0301", "Case", " spaced ", "segment\u2028key", "close]]key]=]"]
        unblocked = ["é", "case", "spaced"]
        first = {key: f"first 𐍈 {key}" for key in [*blocked, *unblocked]}
        second = {key: f"second 𥹉 {key}" for key in first}
        for name, values in (("first.json", first), ("second.json", second)):
            (self.directory / name).write_text(json.dumps(values, ensure_ascii=False), encoding="utf-8")
        sources = ((["-b", ",".join(blocked)], None), (["-B", "-"], ("\n".join(blocked) + "\n").encode("utf-8-sig")))
        for options, data in sources:
            with self.subTest(options=options):
                with patch.dict(os.environ, {"PYTHONIOENCODING": "ascii"}):
                    result = self.cli("manual", *options, "first.json", "second.json", input=data)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertTrue(result.stdout.startswith(b"--[==[\nBLOCKED STRINGS\n"))
                self.assertIn("\trare𐍈𥹉\n".encode(), result.stdout)
                self.assertIn(b"]==]\nreturn {\n", result.stdout)
                with LuaTable(result.stdout) as table:
                    for key in blocked:
                        self.assertEqual(table.row(key, 2), [first[key], first[key]])
                    for key in unblocked:
                        self.assertEqual(table.row(key, 2), [first[key], second[key]])

    def test_unmatched_or_empty_blocked_lists_keep_output_identical(self):
        (self.directory / "empty.txt").write_bytes(b"")
        for command, specific in (
            ("auto", ["--manifest", "manifest.json", "--assets-base", "objects", "en_us", "zh_tw"]),
            ("manual", ["en_us.json", "zh_tw.json"]),
        ):
            expected = self.cli(command, *specific)
            self.assertEqual(expected.returncode, 0, expected.stderr)
            for options in (["-b", ""], ["-b", "item.test,ITEM.TEST2, item.test2"], ["-B", "empty.txt"]):
                with self.subTest(command=command, options=options):
                    result = self.cli(command, *options, *specific)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stdout, expected.stdout)

    def test_invalid_blocked_input_keeps_existing_output(self):
        output = self.directory / "result.lua"
        output.write_bytes(b"previous output")
        (self.directory / "invalid.txt").write_bytes(b"\xffnot-utf8")
        for command, specific in (
            ("auto", ["--manifest", "manifest.json", "--assets-base", "objects", "en_us", "zh_tw"]),
            ("manual", ["en_us.json", "zh_tw.json"]),
        ):
            for source in ("missing.txt", "invalid.txt", "-"):
                with self.subTest(command=command, source=source):
                    result = self.cli(command, "-B", source, "-o", str(output), *specific, input=b"\xffnot-utf8" if source == "-" else None)
                    self.assertEqual(result.returncode, 2)
                    self.assertEqual(result.stdout, b"")
                    self.assertNotIn(b"Traceback", result.stderr)
                    self.assertEqual(output.read_bytes(), b"previous output")

    def test_version_listing_does_not_read_blocked_inputs(self):
        expected = self.cli("auto", "--manifest", "manifest.json", "-l")
        self.assertEqual(expected.returncode, 0, expected.stderr)
        for source in ("missing.txt", "-"):
            with self.subTest(source=source):
                result = self.cli("-B", source, "auto", "--manifest", "manifest.json", "-l", input=b"\xffnot-utf8")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, expected.stdout)

    def test_invalid_auto_languages_do_not_read_blocked_stdin(self):
        for languages, message in (([], "at least one LANGUAGE"), (["bad-code"], "invalid language code"), (["en_us", "EN_US"], "must not be repeated")):
            with self.subTest(languages=languages):
                with patch.object(generator.sys, "stdin", io.StringIO("must remain unread")):
                    with patch.object(generator.Downloader, "open", side_effect=AssertionError("unexpected source access")):
                        with contextlib.redirect_stderr(io.StringIO()) as stderr:
                            with self.assertRaises(SystemExit) as error:
                                generator.main(["auto", "-B", "-", *languages])
                self.assertEqual(error.exception.code, 2)
                self.assertIn(message, stderr.getvalue())

    def test_stdout_stays_utf8_with_ascii_terminal_encoding(self):
        with patch.dict(os.environ, {"PYTHONIOENCODING": "ascii"}):
            default = self.cli("manual", "en_us.json", "zh_hk.json")
            explicit = self.cli("manual", "-o", "-", "en_us.json", "zh_hk.json")
        self.assertEqual(default.returncode, 0, default.stderr)
        self.assertEqual(explicit.returncode, 0, explicit.stderr)
        self.assertEqual(default.stdout, explicit.stdout)
        self.assertIn("𥹉".encode("utf-8"), default.stdout)
        self.assertFalse((self.directory / "result.lua").exists())

    def test_help_for_each_subcommand(self):
        for command, positional in (("auto", "LANGUAGE"), ("manual", "JSON")):
            with self.subTest(command=command):
                result = self.cli(command, "--help")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertTrue(result.stdout.startswith(f"usage: generator.py {command} [-h]".encode()))
                for option in (rb"-h, --help", rb"-e(?: ENCODING)?, --encoding ENCODING", rb"-o(?: OUTPUT)?, --output OUTPUT"):
                    self.assertRegex(result.stdout, option)
                self.assertIn(b"default: STDOUT", result.stdout)
                self.assertIn(b"global options:", result.stdout)
                self.assertIn(positional.encode(), result.stdout)
                self.assertNotIn(b"--languages", result.stdout)
                self.assertNotIn(b"default: en_us", result.stdout)
                if command == "auto":
                    self.assertRegex(result.stdout, rb"-v(?: VERSION)?, --version VERSION")
                    self.assertIn(b"-l, --list-versions", result.stdout)

    def test_global_options_in_both_positions_are_preserved(self):
        make_fixture(self.directory, encoding="gb18030")
        for command, specific in (
            ("auto", ["--manifest", "manifest.json", "--assets-base", "objects", "en_us", "zh_hk"]),
            ("manual", ["en_us.json", "zh_hk.json"]),
        ):
            for encoding_option, output_option in (("-e", "-o"), ("--encoding", "--output")):
                for before_subcommand in (True, False):
                    with self.subTest(command=command, encoding_option=encoding_option, before_subcommand=before_subcommand):
                        global_options = [encoding_option, "gb18030", output_option, "global.lua"]
                        arguments = [*global_options, command, *specific] if before_subcommand else [command, *global_options, *specific]
                        result = self.cli(*arguments)
                        self.assertEqual(result.returncode, 0, result.stderr)
                        self.assertEqual(result.stdout, b"")
                        with LuaTable((self.directory / "global.lua").read_bytes()) as table:
                            self.assertEqual(table.row("quote.test", 2), [self.translations["en_us"]["quote.test"], "𥹉"])

    def test_explicit_global_option_after_subcommand_takes_precedence(self):
        result = self.cli("--output", "unused.lua", "manual", "--output", "chosen.lua", "en_us.json")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, b"")
        self.assertFalse((self.directory / "unused.lua").exists())
        self.assertTrue((self.directory / "chosen.lua").exists())

    def test_global_output_applies_to_version_listing(self):
        result = self.cli("--output", "versions.txt", "auto", "--manifest", "manifest.json", "--list-versions")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, b"")
        self.assertEqual((self.directory / "versions.txt").read_bytes().splitlines()[0], b"VERSION        TYPE  RELEASE_TIME")

    def test_output_option_requires_an_argument(self):
        for arguments in (("--output",), ("manual", "en_us.json", "--output"), ("auto", "--output")):
            with self.subTest(arguments=arguments):
                result = self.cli(*arguments)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, b"")
                self.assertIn(b"expected one argument", result.stderr)
                self.assertFalse((self.directory / "result.lua").exists())

    def test_zero_padded_keys_with_gothic_values_are_not_lost(self):
        english = {"key.keyboard.keypad.0": "Keypad 0", "key.keyboard.keypad.00": "Keypad 00", "key.keyboard.keypad.000": "Keypad 000"}
        gothic = {"key.keyboard.keypad.0": "𐍂𐌰𐌸 0", "key.keyboard.keypad.00": "𐍂𐌰𐌸 00", "key.keyboard.keypad.000": "𐍂𐌰𐌸 000"}
        for code, values in (("en_us", english), ("got_de", gothic)):
            (self.directory / f"{code}.json").write_text(json.dumps(values, ensure_ascii=False), encoding="utf-8")
        result = self.cli("manual", "en_us.json", "got_de.json")
        self.assertEqual(result.returncode, 0, result.stderr)
        with LuaTable(result.stdout) as table:
            for key in english:
                self.assertEqual(table.row(key, 2), [english[key], gothic[key]])

    def test_local_manifest_and_relative_metadata(self):
        result = self.cli("auto", "--manifest", "manifest.json", "--assets-base", "objects", "en_us", "zh_cn", "zh_tw", "zh_hk")
        self.assertEqual(result.returncode, 0, result.stderr)
        output = result.stdout
        self.assertTrue(output.startswith(b"-- version: snapshot-test\n-- asset: assets.json (2026-10-06T13:00:46+00:00)\nreturn {\n"))
        with LuaTable(output) as table:
            self.assertEqual(table.row("item.test2", 4), ["Two", "二", "貳", "Two"])

    def test_version_selection(self):
        for option in ("-v", "--version"):
            for selector, expected in (("latest", "snapshot-test"), ("latest-snapshot", "snapshot-test"), ("latest-release", "release-test"), ("release-test", "release-test")):
                with self.subTest(option=option, version=selector):
                    result = self.cli("auto", "--manifest", "manifest.json", "--assets-base", "objects", option, selector, "lzh", "en_us")
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn(f"[ '_meta.version' ] = \"{expected}\"".encode(), result.stdout)

    def test_auto_requires_languages_before_reading_manifest(self):
        with patch.object(generator.Downloader, "open", side_effect=AssertionError("unexpected source access")):
            with contextlib.redirect_stderr(io.StringIO()) as stderr:
                with self.assertRaises(SystemExit) as error:
                    generator.main(["auto"])
        self.assertEqual(error.exception.code, 2)
        self.assertIn("at least one LANGUAGE", stderr.getvalue())
        result = self.cli("-o", "result.lua", "auto", "--manifest", "missing.json")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, b"")
        self.assertIn(b"at least one LANGUAGE", result.stderr)
        self.assertFalse((self.directory / "result.lua").exists())

    def test_auto_uses_first_language_even_when_english_is_present(self):
        result = self.cli("auto", "--manifest", "manifest.json", "--assets-base", "objects", "zh_tw", "en_us", "zh_hk")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn(b"item.test10", result.stdout)
        self.assertNotIn(b"only.english", result.stdout)
        with LuaTable(result.stdout) as table:
            self.assertEqual(table.row("item.test2", 3), ["貳", "Two", "貳"])

    def test_auto_without_english_does_not_download_client(self):
        (self.directory / "client.jar").unlink()
        version_path = self.directory / "version.json"
        version = json.loads(version_path.read_bytes())
        del version["downloads"]
        version_path.write_text(json.dumps(version), encoding="utf-8")
        result = self.cli("auto", "--manifest", "manifest.json", "--assets-base", "objects", "lzh", "zh_hk")
        self.assertEqual(result.returncode, 0, result.stderr)
        with LuaTable(result.stdout) as table:
            self.assertEqual(table.row("item.test2", 2), ["兩", "兩"])
            self.assertEqual(table.row("quote.test", 2), ["曰", "𥹉"])

    def test_auto_explicit_input_encoding_does_not_change_metadata_encoding(self):
        make_fixture(self.directory, encoding="gb18030")
        result = self.cli("auto", "--manifest", "manifest.json", "--assets-base", "objects", "--encoding", "gb18030", "en_us", "zh_hk")
        self.assertEqual(result.returncode, 0, result.stderr)
        with LuaTable(result.stdout) as table:
            self.assertEqual(table.row("quote.test", 2), [self.translations["en_us"]["quote.test"], "𥹉"])

    def test_list_versions_reads_only_manifest_and_uses_stdout(self):
        manifest_path = self.directory / "manifest.json"
        manifest = json.loads(manifest_path.read_bytes())
        for entry, kind in zip(manifest["versions"], ("snapshot", "release")):
            entry["type"] = kind
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        for filename in ("version.json", "assets.json", "client.jar"):
            (self.directory / filename).unlink()
        expected = (
            b"VERSION        TYPE      RELEASE_TIME\n"
            b"-------------  --------  -------------------------\n"
            b"snapshot-test  snapshot  2026-10-06T13:00:46+00:00\n"
            b"release-test   release   2025-07-17T12:04:02+00:00\n"
        )
        for option in ("-l", "--list-versions"):
            with self.subTest(option=option):
                result = self.cli("auto", "--manifest", "manifest.json", option)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, expected)
        self.assertFalse((self.directory / "result.lua").exists())
        saved = self.cli("auto", "--manifest", "manifest.json", "-l", "-o", "versions.txt")
        self.assertEqual(saved.returncode, 0, saved.stderr)
        self.assertEqual(saved.stdout, b"")
        self.assertEqual((self.directory / "versions.txt").read_bytes(), expected)

    def test_list_versions_aligns_long_fields_and_empty_values(self):
        manifest = {"versions": [{"id": "a-very-long-version", "type": "custom-release-type", "releaseTime": "short-time"}, {"id": "x"}]}
        (self.directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        result = self.cli("auto", "--manifest", "manifest.json", "-l")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn(b"\t", result.stdout)
        lines = result.stdout.decode().splitlines()
        self.assertEqual(lines[1], "-------------------  -------------------  ------------")
        self.assertEqual(lines[0].index("TYPE"), lines[2].index("custom-release-type"))
        self.assertEqual(lines[0].index("RELEASE_TIME"), lines[2].index("short-time"))
        self.assertEqual(lines[3], "x")
        self.assertTrue(all(line == line.rstrip() for line in lines))

    def test_online_manifest_and_asset_mirror(self):
        class QuietHandler(SimpleHTTPRequestHandler):
            def log_message(self, *arguments):
                pass

        try:
            server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(self.directory)))
        except PermissionError:
            self.skipTest("sandbox disallows sockets; rerun outside that sandbox to test HTTP sources")
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_port}"
            with patch.dict(os.environ, {"NO_PROXY": "127.0.0.1", "no_proxy": "127.0.0.1"}):
                result = self.cli("auto", "--manifest", base + "/manifest.json", "--assets-base", base + "/objects", "lzh", "zh_hk")
            self.assertEqual(result.returncode, 0, result.stderr)
            with LuaTable(result.stdout) as table:
                self.assertEqual(table.row("quote.test", 2), ["曰", "𥹉"])
            (self.directory / "version.json").unlink()
            with patch.dict(os.environ, {"NO_PROXY": "127.0.0.1", "no_proxy": "127.0.0.1"}):
                listed = self.cli("auto", "--manifest", base + "/manifest.json", "--list-versions")
            self.assertEqual(listed.returncode, 0, listed.stderr)
            self.assertIn(b"snapshot-test", listed.stdout)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_original_outputs_match_fixed_baselines(self):
        for flavor, languages in (("zh", ["en_us", "zh_cn", "zh_tw", "zh_hk"]), ("lzh", ["en_us", "lzh"])):
            for mode in ("manual", "auto"):
                with self.subTest(mode=mode, flavor=flavor):
                    expected = (ROOT / "tests" / "fixtures" / f"{mode}-{flavor}.lua").read_bytes()
                    if mode == "auto":
                        result = self.cli("auto", "--manifest", "manifest.json", "--assets-base", "objects", *languages)
                    else:
                        result = self.cli("manual", *[str(self.files[code]) for code in languages])
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stdout, expected)

    def test_json_encodings_preserve_rare_characters(self):
        rare = '𐌰𐌹𐍈 𥹉 𠀀 \ue000 e\u0301 اَلْمَلَايُو ಕನ್ನಡ ລາວ עברית " \\ \n\t\r\b\f\x00\x017'
        key = "rare'\\\n\x00𐍈"
        values = {key: rare, "empty": ""}
        reference = None
        for encoding in ("utf-8", "utf-8-sig", "utf-16", "utf-16-le", "utf-16-be", "utf-32", "utf-32-le", "utf-32-be"):
            for escaped in (False, True):
                with self.subTest(encoding=encoding, escaped=escaped):
                    path = self.directory / "encoded.json"
                    path.write_bytes(json.dumps(values, ensure_ascii=escaped).encode(encoding))
                    result = self.cli("manual", str(path))
                    self.assertEqual(result.returncode, 0, result.stderr)
                    output = result.stdout
                    if reference is None:
                        reference = output
                    self.assertEqual(output, reference)
                    self.assertNotIn(b"\\u", output)
                    with LuaTable(output) as table:
                        self.assertEqual(table.row(key, 1), [rare])
                        self.assertEqual(table.row("empty", 1), [""])

    def test_explicit_legacy_encoding(self):
        path = self.directory / "gb.json"
        path.write_bytes(json.dumps({"name": "𥹉龘中文"}, ensure_ascii=False).encode("gb18030"))
        result = self.cli("manual", "--encoding", "gb18030", str(path))
        self.assertEqual(result.returncode, 0, result.stderr)
        with LuaTable(result.stdout) as table:
            self.assertEqual(table.row("name", 1), ["𥹉龘中文"])

    def test_invalid_input_keeps_existing_output(self):
        output = self.directory / "result.lua"
        output.write_bytes(b"previous output")
        cases = [
            ("manual",),
            ("manual", "missing.json"),
            ("manual", "--version-note", "crowdin", "en_us.json"),
            ("manual", "--asset-note", "2026-10-06", "en_us.json"),
            ("manual", "--version", "bad\nversion", "en_us.json"),
            ("manual", "--asset", "bad\rasset", "en_us.json"),
            ("manual", "--version", "snapshot-test", "--version-note", "bad\nnote", "en_us.json"),
            ("manual", "--asset", "assets.json", "--asset-note", "bad\nnote", "en_us.json"),
            ("auto", "en_us", "en_us"),
            ("manual", "en_us.json", "--encoding", "unknown-encoding"),
            ("auto", "--encoding", "unknown-encoding"),
            ("auto", "--manifest", "manifest.json", "--version", "missing-version", "en_us"),
            ("auto", "--manifest", "manifest.json", "not_a_language"),
            ("auto", "--timeout", "nan"),
            ("auto", "--timeout", "0"),
            ("auto", "--manifest", "ftp://example.com/manifest.json", "en_us"),
        ]
        for arguments in cases:
            with self.subTest(arguments=arguments):
                result = self.cli(*arguments, "-o", str(output))
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn(b"Traceback", result.stderr)
                self.assertEqual(output.read_bytes(), b"previous output")
        for content in (b"not JSON", b"[]", b'{"key": 42}', b'{"key": "\\ud800"}', b'{"key": "\xff"}'):
            with self.subTest(content=content):
                self.files["en_us"].write_bytes(content)
                result = self.cli("manual", "-o", str(output), "en_us.json")
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn(b"Traceback", result.stderr)
                self.assertEqual(output.read_bytes(), b"previous output")

    def test_version_sort_suffix_edge_cases(self):
        # Fixed modern GNU ordering, independent of the installed sort version.
        cases = [
            ["dl.a", "dl5", "dl.a.", "dl_a"],
            ["a01.a", "a1.a", "a001.b", "a1.z"],
            [".0", "..a", ".9", ".a", ".a.b"],
            ["a~", "a0~", "a", "a0", "a00"],
        ]
        for expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(sorted(reversed(expected), key=generator.VersionKey), expected)

    def test_version_sort_matches_gnu_sort_V(self):
        for name in ("sort", "gnusort"):
            command = shutil.which(name)
            if command:
                version = subprocess.run([command, "--version"], text=True, capture_output=True)
                if version.returncode == 0 and "(GNU coreutils)" in version.stdout:
                    break
        else:
            self.skipTest("GNU sort is not installed")

        def reference(values):
            return subprocess.run([command, "-V"], input="\n".join(values) + "\n", text=True, capture_output=True, check=True, env={**os.environ, "LC_ALL": "C.UTF-8"}).stdout.splitlines()

        rng = random.Random(5)
        keys = ["", ".", "..", ".a", ".a.b", "a~", "a~1", "a0", "a", "a1", "a01", "a2.b", "a10.b", "a1.0", "a1.a", "a2.a", "a1_a", "a1_2", "a1_10", "a0~", "a00", "𐍈2", "𐍈10", "a.𐍈"]
        keys += ["".join(rng.choice(string.ascii_letters + string.digits + "._~+-") for _ in range(rng.randint(1, 35))) for _ in range(2000)]
        if reference(["a.b.", "a1"]) == ["a.b.", "a1"]:
            # GNU 8.32 strips trailing dots as suffixes. Compare shared cases;
            # the fixed cases above always verify modern suffix ordering.
            keys = [key for key in keys if key in (".", "..") or not key.endswith(".")]
        self.assertEqual(sorted(keys, key=generator.VersionKey), reference(keys))


if __name__ == "__main__":
    unittest.main()
