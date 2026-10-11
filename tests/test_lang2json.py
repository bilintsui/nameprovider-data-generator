import codecs
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from lua_runtime import LuaTable
from support import ROOT
import lang2json


class LangConversionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="nameprovider-lang-test-")
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)

    def cli(self, *arguments, input=None, env=None):
        return subprocess.run([sys.executable, str(ROOT / "lang2json.py"), *arguments], cwd=self.directory, input=input, capture_output=True, timeout=20, env=env)

    def write(self, filename, contents):
        path = self.directory / filename
        path.write_bytes(contents.encode("utf-8") if isinstance(contents, str) else contents)
        return path

    def test_no_arguments_only_show_help(self):
        before = set(self.directory.iterdir())
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.startswith(b"usage: lang2json.py [-h] [-e ENCODING] [-o OUTPUT]"))
        self.assertIn(b"-h, --help", result.stdout)
        self.assertEqual(set(self.directory.iterdir()), before)

    def test_comment_rules_and_literal_punctuation(self):
        contents = (
            "## header\r\n"
            "  ### indented comment\r\n"
            "# standalone compatibility comment\r\n"
            "\t \r\n"
            "tab=Text\t# terminator\r\n"
            "multiple=Text\t\t### comment\r\n"
            "inline=Text##comment\r\n"
            "spaced=Text ###comment\r\n"
            "spaces=  Text  \t##comment\r\n"
            "first=Keep##comment\t#later\r\n"
            "second=Keep\t#comment##later\r\n"
            "hash=Rank #1 in #channel\r\n"
            "url=https://example.test/?a=b&c=d#section\r\n"
            "slashes=// literal /* text */\r\n"
            "equals=a=b=c\r\n"
            "tabs=Text\t\t\r\n"
            "empty=\t#comment\r\n"
        )
        expected = {
            "tab": "Text", "multiple": "Text", "inline": "Text", "spaced": "Text ",
            "spaces": "  Text  ", "first": "Keep", "second": "Keep",
            "hash": "Rank #1 in #channel", "url": "https://example.test/?a=b&c=d#section",
            "slashes": "// literal /* text */", "equals": "a=b=c", "tabs": "Text\t\t", "empty": "",
        }
        self.assertEqual(lang2json.parse_lang(contents.encode(), "comments.lang"), expected)

    def test_format_markers_and_backslashes_are_preserved(self):
        expected = {
            "formats": "%s %2$s %d %1$d %.2f %1 %% 100% %1 $s §a",
            "url": "https://example.test/%28name%29",
            "backslash": "\\", "escape": r'line\nnext \" \M \ ',
            "next": "separate record",
        }
        contents = "\n".join(f"{key}={value}" for key, value in expected.items())
        self.assertEqual(lang2json.parse_lang(contents.encode(), "literal.lang"), expected)

    def test_translate_parser_escapes_literal_percents_and_url_encodings(self):
        cases = (
            ("100% accurate; 1% packet loss; -100%", "100%% accurate; 1%% packet loss; -100%%"),
            ("The % of players; Amount %; %1$s%", "The %% of players; Amount %%; %1$s%%"),
            ("%1$d% %.2f%", "%1$s%% %%.2f%%"),
            ("https://example.test/%28name%29?q=%E4%B8%AD&rate=100%", "https://example.test/%%28name%%29?q=%%E4%%B8%%AD&rate=100%%"),
            ('https://example.test/%28a%29" next=%28', 'https://example.test/%%28a%%29" next=%2$s8'),
            ("https://example.test/%20$s/%20$d/%2$d/%2$h/%s", "https://example.test/%20$s/%20$d/%2$s/%2$s$h/%s"),
            ("custom+link://example.test/%02/%AF?q=%2f outside=%2f", "custom+link://example.test/%%02/%%AF?q=%%2f outside=%2$sf"),
            ("%s %2$s %% %%%s %%%% %%28", "%s %2$s %%%% %%%%%s %%%%%%%% %%%2$s8"),
            ("𠮷\u0301\u2067 50%\u2028ᐃ %1$s%\ufeff", "𠮷\u0301\u2067 50%%\u2028ᐃ %1$s%%\ufeff"),
        )
        for original, expected in cases:
            with self.subTest(original=original):
                actual = lang2json.translate_parser_string("key", original)
                self.assertEqual(actual, expected)

    def test_translate_parser_counts_original_percent_runs_once(self):
        for count in range(1, 9):
            with self.subTest(count=count):
                run = "%" * count
                self.assertEqual(lang2json.translate_parser_string("key", run), "%" * (2 * count))
                self.assertEqual(lang2json.translate_parser_string("key", run + "s"), "%" * (2 * count - 1) + "s")
                self.assertEqual(lang2json.translate_parser_string("key", run + "1"), "%" * (2 * count - 1) + "1$s")
        self.assertEqual(lang2json.translate_parser_string("key", "%1%%"), "%1$s%%%%")
        self.assertEqual(lang2json.translate_parser_string("key", "%%d"), "%%%s")

    def test_translate_parser_adapts_bare_indices_without_renumbering(self):
        cases = (
            ("%1 %12 / %2; %1%1", "%1$s %1$s2 / %2$s; %1$s%1$s"),
            ("(%1). %2! %3?", "(%1$s). %2$s! %3$s?"),
            ("%s then %2 and %1$s then %s", "%s then %2$s and %1$s then %s"),
            ("%4%%; %2$s %1", "%4$s%%%%; %2$s %1$s"),
            ("%0 %02 %0012 %02d %03d", "%0$s %0$s2 %0$s012 %0$s2d %0$s3d"),
            ("%9 %10 %100 %123", "%9$s %1$s0 %1$s00 %1$s23"),
            ("%９ %٢ %𝟙", "%%９ %%٢ %%𝟙"),
            ("%1件𰻞 %2\u2028I\u0307", "%1$s件𰻞 %2$s\u2028I\u0307"),
        )
        for original, expected in cases:
            with self.subTest(original=original):
                actual = lang2json.translate_parser_string("key", original)
                self.assertEqual(actual, expected)
        for index in range(10):
            with self.subTest(index=index):
                self.assertEqual(lang2json.translate_parser_string("key", f"%{index}"), f"%{index}$s")

    def test_translate_parser_adapts_integer_and_literal_float_markers(self):
        cases = (
            ("%s %d %2$d / %1$s / %0$d / %9$d", "%s %s %2$s / %1$s / %0$s / %9$s"),
            ("%f / %.2f / %1$f / %1.2f", "%%f / %%.2f / %1$s$f / %1$s.2f"),
            ("%2$%d / %1$%s", "%2$s$%s / %1$s$%s"),
            ("%  s %X %? %S %h %", "%%  s %%X %%? %%S %%h %%"),
        )
        for original, expected in cases:
            with self.subTest(original=original):
                self.assertEqual(lang2json.translate_parser_string("key", original), expected)

    def test_translate_parser_preserves_multi_digit_typed_and_invalid_formats(self):
        original = "%12$s %02$d %0012$s %100$d"
        self.assertEqual(lang2json.translate_parser_string("key", original), original)
        for key, value in (("translation.test.invalid", "hi %"), ("translation.test.invalid2", "hi %  s"), ("translation.test.invalid3", "%d %f %1 %%")):
            self.assertEqual(lang2json.translate_parser_string(key, value), value)

    def test_translate_parser_preserves_literal_suffixes_after_bare_indices(self):
        cases = (
            ("%1s %2d %12s", "%1$ss %2$sd %1$s2s"),
            ("%1$ %2$S %3$h", "%1$s$ %2$s$S %3$s$h"),
            ("%1s %1$s %1$d %2$f", "%1$ss %1$s %1$s %2$s$f"),
            ("%1 $s / %1 X $d / %1\u00a0$s", "%1$s $s / %1$s X $d / %1$s\u00a0$s"),
            ("$s $d $f $S $h $ / %1$", "$s $d $f $S $h $ / %1$s$"),
            ("§a@&special& %1\x00$d\\n\x01\ufeff", "§a@&special& %1$s\x00$d\\n\x01\ufeff"),
            ("𠮷 %1s\u2028ᐃ %2$\u2067", "𠮷 %1$ss\u2028ᐃ %2$s$\u2067"),
        )
        for original, expected in cases:
            with self.subTest(original=original):
                actual = lang2json.translate_parser_string("key", original)
                self.assertEqual(actual, expected)

    def test_translate_parser_literal_percentage_exception_is_key_and_shape_scoped(self):
        cases = (
            ("options.languageWarning", "prefix %100 suffix", "prefix %%100 suffix"),
            ("options.languageWarning", "%100! / %100", "%%100! / %%100"),
            ("options.languageWarning", "%1000 %100s %100$s %100$d", "%1$s000 %1$s00s %100$s %100$d"),
            ("options.languageWarning", "%%100 / %1$s00", "%%%1$s00 / %1$s00"),
            ("other.key", "prefix %100 suffix", "prefix %1$s00 suffix"),
            ("options.languageWarning.extra", "%100", "%1$s00"),
        )
        for key, original, expected in cases:
            with self.subTest(key=key, original=original):
                self.assertEqual(lang2json.translate_parser_string(key, original), expected)

    def test_translate_parser_cli_is_explicit_and_only_changes_values(self):
        records = {"50%key": "𠮷 100% accurate", "url": "https://example.test/%28name%29", "indices": "%2 / %1", "native": "%%%s %s %2$s %1 $s", "translation.test.invalid": "hi %"}
        contents = "\n".join(f"{key}={value}" for key, value in records.items()).encode()
        raw = self.cli("-", input=contents)
        self.assertEqual(raw.returncode, 0, raw.stderr)
        self.assertEqual(json.loads(raw.stdout), records)
        for option in ("-t", "--translate-parser"):
            result = self.cli(option, "-", input=contents)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), {"50%key": "𠮷 100%% accurate", "url": "https://example.test/%%28name%%29", "indices": "%2$s / %1$s", "native": "%%%%%s %s %2$s %1$s $s", "translation.test.invalid": "hi %"})

    def test_prepared_languages_merge_and_survive_generator_lua_output(self):
        self.write("base.lang", "shared=%f\nshared=%d / %12 / %%s\nonly.first=https://example.test/%28\nempty=\n")
        self.write("extra.lang", "shared=Lower priority\nsupplement=%1 X $d\nempty=%d\n")
        self.write("second.lang", "shared=%2d\nextra.second=%s\nempty=\n")
        first = self.cli("base.lang", "-t", "extra.lang", "-o", "first.json")
        second = self.cli("-t", "second.lang", "-o", "second.json")
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)
        result = subprocess.run([sys.executable, str(ROOT / "generator.py"), "manual", "first.json", "second.json"], cwd=self.directory, capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        with LuaTable(result.stdout) as table:
            self.assertEqual(table.row("shared", 2), ["%s / %1$s2 / %%%s", "%2$sd"])
            self.assertEqual(table.row("supplement", 2), ["%1$s X $d", "%1$s X $d"])
            self.assertEqual(table.row("only.first", 2), ["https://example.test/%%28", "https://example.test/%%28"])
            self.assertEqual(table.row("empty", 2), ["", ""])
            with self.assertRaisesRegex(AssertionError, "expected a Lua table"):
                table.row("extra.second", 2)

    def test_merge_uses_union_first_file_and_last_record(self):
        self.write("vanilla.lang", "shared=Base\nonly.first=First\nduplicate=old\nduplicate=new\nempty=\n")
        self.write("補充.lang", "shared=Extra\nonly.second=Second\nempty=Lower priority\n")
        result = self.cli("vanilla.lang", "補充.lang")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"shared": "Base", "only.first": "First", "duplicate": "new", "empty": "", "only.second": "Second"})
        reverse = self.cli("補充.lang", "vanilla.lang")
        self.assertEqual(reverse.returncode, 0, reverse.stderr)
        self.assertEqual(json.loads(reverse.stdout)["shared"], "Extra")
        self.assertEqual(json.loads(reverse.stdout)["empty"], "Lower priority")

    def test_reversing_earlier_override_order_preserves_values(self):
        sources = (
            ("extra.lang", "shared=Extra\nextra=Only extra\nempty=Extra\n"),
            ("ui.lang", "shared=Old UI\nshared=UI\nui=Only UI\nempty=UI\n"),
            ("vanilla.lang", "shared=Base\nbase=Only base\nempty=\n"),
        )
        old_result = {}
        for filename, contents in sources:
            self.write(filename, contents)
            old_result.update(lang2json.parse_lang(contents.encode(), filename))
        converted = self.cli(*(filename for filename, _ in reversed(sources)))
        self.assertEqual(converted.returncode, 0, converted.stderr)
        self.assertEqual(json.loads(converted.stdout), old_result)

    def test_stdin_participates_in_file_order(self):
        self.write("before.lang", "key=Before\nfirst=First\n")
        self.write("after.lang", "key=After\nlast=Last\n")
        result = self.cli("before.lang", "-", "after.lang", input=b"key=STDIN\nmiddle=Middle\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"key": "Before", "first": "First", "middle": "Middle", "last": "Last"})
        result = self.cli("before.lang", "-", input=b"key=STDIN\n")
        self.assertEqual(json.loads(result.stdout)["key"], "Before")
        result = self.cli("-", "after.lang", input=b"key=STDIN\n")
        self.assertEqual(json.loads(result.stdout)["key"], "STDIN")
        result = self.cli("-", "-", input=b"key=STDIN\n")
        self.assertEqual(result.returncode, 2)
        self.assertIn(b"STDIN (-) can only be read once", result.stderr)
        self.assertEqual(result.stdout, b"")

    def test_output_option_requires_a_value_and_accepts_stdout(self):
        self.write("input.lang", "key=𠮷\n")
        default = self.cli("input.lang")
        explicit = self.cli("input.lang", "-o", "-")
        self.assertEqual(default.returncode, 0, default.stderr)
        self.assertEqual(explicit.returncode, 0, explicit.stderr)
        self.assertEqual(default.stdout, explicit.stdout)
        missing = self.cli("input.lang", "--output")
        self.assertEqual(missing.returncode, 2)
        self.assertIn(b"expected one argument", missing.stderr)

    def test_options_can_appear_among_files(self):
        self.write("first.lang", "key=前\n")
        self.write("last.lang", "key=後\n")
        result = self.cli("first.lang", "-o", "合併.json", "last.lang", "--encoding", "utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, b"")
        self.assertEqual(json.loads((self.directory / "合併.json").read_bytes()), {"key": "前"})

    def test_default_decoding_handles_boms_per_file(self):
        text = "键𠮷=I\u0307 𰻞\n"
        for encoding, bom in (("utf-8", b""), ("utf-8", codecs.BOM_UTF8), ("utf-16-le", codecs.BOM_UTF16_LE), ("utf-16-be", codecs.BOM_UTF16_BE), ("utf-32-le", codecs.BOM_UTF32_LE), ("utf-32-be", codecs.BOM_UTF32_BE)):
            with self.subTest(encoding=encoding, bom=bom):
                result = self.cli("-", input=bom + text.encode(encoding))
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout), {"键𠮷": "I\u0307 𰻞"})
                self.assertFalse(result.stdout.startswith(codecs.BOM_UTF8))
                self.assertIn("𰻞".encode(), result.stdout)
        self.write("utf8.lang", text)
        self.write("utf16.lang", "other=ᐃᓄᒃᑎᑐᑦ\n".encode("utf-16"))
        mixed = self.cli("utf8.lang", "utf16.lang")
        self.assertEqual(mixed.returncode, 0, mixed.stderr)
        self.assertEqual(json.loads(mixed.stdout), {"键𠮷": "I\u0307 𰻞", "other": "ᐃᓄᒃᑎᑐᑦ"})

    def test_explicit_encoding_and_strict_rejection(self):
        text = "键𠮷=𰻞 汉字\n"
        result = self.cli("-e", "gb18030", "-", input=text.encode("gb18030"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"键𠮷": "𰻞 汉字"})
        self.assertEqual(lang2json.parse_lang(codecs.BOM_UTF8 + b"key=value", "bom.lang", "utf-8"), {"key": "value"})
        for encoding in (None, "utf-8", "utf-8-sig"):
            with self.subTest(encoding=encoding):
                self.assertEqual(lang2json.parse_lang(codecs.BOM_UTF8 + "\ufeffkey=value".encode(), "bom.lang", encoding), {"\ufeffkey": "value"})
        for options, data in (([], b"key=\xff"), ([], b"key=\xed\xa0\x80"), (["-e", "ascii"], "key=𠮷".encode()), (["-e", "utf-16-le"], b"k\x00=\x00\x00\xd8")):
            with self.subTest(options=options, data=data):
                result = self.cli(*options, "-", input=data)
                self.assertEqual(result.returncode, 2)
                self.assertIn(b"STDIN: cannot decode input", result.stderr)
                self.assertEqual(result.stdout, b"")
        invalid = self.cli("-e", "unknown-encoding", "-")
        self.assertEqual(invalid.returncode, 2)
        self.assertIn(b"unknown encoding", invalid.stderr)

    def test_unicode_separators_do_not_change_line_numbers(self):
        records = "𠮷\u2028键=A\u0085B\u2028C\u2029D\nnext=Second\ninvalid"
        with self.assertRaisesRegex(lang2json.ConversionError, r"separators\.lang:3: expected KEY=VALUE"):
            lang2json.parse_lang(records.encode(), "separators.lang")

    def test_invalid_input_does_not_write_partial_output(self):
        self.write("valid.lang", "key=Valid\n")
        self.write("invalid.lang", "valid=First\n=empty key\n")
        output = self.write("output.json", "keep existing file")
        for options in ([], ["-o", "output.json"]):
            with self.subTest(options=options):
                result = self.cli(*options, "valid.lang", "invalid.lang")
                self.assertEqual(result.returncode, 2)
                self.assertIn(b"invalid.lang:2: empty key", result.stderr)
                self.assertEqual(result.stdout, b"")
                self.assertEqual(output.read_text(), "keep existing file")
        missing = self.cli("valid.lang", "missing.lang", "-o", "new.json")
        self.assertEqual(missing.returncode, 2)
        self.assertIn(b"missing.lang", missing.stderr)
        self.assertFalse((self.directory / "new.json").exists())

    def test_empty_input_is_an_empty_json_object(self):
        result = self.cli("-", input=codecs.BOM_UTF8 + b"## comment\r\n\r\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {})
        missing = self.cli("-o", "unused.json")
        self.assertEqual(missing.returncode, 2)
        self.assertFalse((self.directory / "unused.json").exists())

    def test_output_is_utf8_even_with_ascii_terminal_encoding(self):
        result = self.cli("-", input="key=𠮷ᐃ\n".encode(), env={**os.environ, "PYTHONIOENCODING": "ascii"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"key": "𠮷ᐃ"})
        self.assertIn("𠮷ᐃ".encode(), result.stdout)

    def test_cold_characters_survive_json_and_lua_51_roundtrip(self):
        groups = (
            "𠮷𪚥𰻞", "𐐀𐐷", "𓂀𓀀", "𝄞𝄢", "👩‍🔬🇨🇳✈️",
            "I\u0307 e\u0301 a\u0308\u0301", "العَرَبِيَّة", "עִבְרִית", "བོད་སྐད་",
            "ភាសាខ្មែរ", "ᏣᎳᎩ", "ᐃᓄᒃᑎᑐᑦ", "\u200e中文\u200f\u2067العربية\u2069",
            "A\u00a0B\u202fC\u2009D\u3000E", "\ue000\uf8ff\U000f0000\U0010fffd",
            "A\u0085B\u2028C\u2029D", "A\ufeffB", "A\x00B\x01C\x07D\x0bE\x0cF\x7fG",
            '\\ " \' /* */ // =', "  preserve both ends  ",
        )
        expected = {"键𠮷." + value: value for value in groups if "=" not in value}
        expected.update({"quotes": groups[-2], "é": "precomposed", "e\u0301": "combining"})
        text = "\n".join(f"{key}={value}" for key, value in expected.items()) + "\n"
        converted = self.cli("-", input=codecs.BOM_UTF8 + text.encode())
        self.assertEqual(converted.returncode, 0, converted.stderr)
        self.assertEqual(json.loads(converted.stdout), expected)
        self.write("language.json", converted.stdout)
        result = subprocess.run([sys.executable, str(ROOT / "generator.py"), "manual", "language.json"], cwd=self.directory, capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        with LuaTable(result.stdout) as table:
            for key, value in expected.items():
                with self.subTest(key=key):
                    actual = table.row(key, 1)[0]
                    self.assertEqual(actual, value)
                    self.assertEqual(actual.encode("utf-8"), value.encode("utf-8"))


if __name__ == "__main__":
    unittest.main()
