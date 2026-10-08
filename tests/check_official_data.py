#!/usr/bin/env python3
"""Download official data, compare auto/manual outputs, and check Lua Unicode."""

import argparse
import collections
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unicodedata
from urllib.request import urlopen
from zipfile import ZipFile

from lua_runtime import LuaRuntimeError, LuaTable
from support import automatic_from_files, generator


ZH_LANGUAGES = ("en_us", "zh_cn", "zh_tw", "zh_hk")
RARE_LANGUAGES = ("got_de", "zlm_arab", "kn_in", "lo_la", "yi_de", "ta_in", "qya_aa", "kw_gb", "gv_im", "mi_nz", "haw_us", "tok", "br_fr")


def download(url, destination, digest=None):
    if not destination.exists():
        with urlopen(url, timeout=60) as response:
            destination.write_bytes(response.read())
    content = destination.read_bytes()
    if digest and hashlib.sha1(content).hexdigest() != digest:
        raise AssertionError(f"SHA-1 mismatch: {destination}")
    return content


def prepare(cache, manifest, version_id):
    entry = next(value for value in manifest["versions"] if value["id"] == version_id)
    directory = cache / version_id
    directory.mkdir(parents=True, exist_ok=True)
    manifest_path = directory / "version_manifest.json"
    manifest_path.write_text(json.dumps({**manifest, "versions": [entry]}), encoding="utf-8")
    version_path = directory / "version.json"
    version = json.loads(download(entry["url"], version_path))
    assets_path = directory / "assets.json"
    index = version["assetIndex"]
    assets = json.loads(download(index["url"], assets_path, index.get("sha1")))
    client_path = directory / "client.jar"
    client = version["downloads"]["client"]
    download(client["url"], client_path, client.get("sha1"))
    with ZipFile(client_path) as archive:
        (directory / "en_us.json").write_bytes(archive.read("assets/minecraft/lang/en_us.json"))
    files = {"en_us": directory / "en_us.json"}
    urls = {
        generator.DEFAULT_MANIFEST: str(manifest_path),
        entry["url"]: str(version_path),
        index["url"]: str(assets_path),
        client["url"]: str(client_path),
    }
    for language in (*ZH_LANGUAGES[1:], "lzh", *RARE_LANGUAGES):
        asset = assets["objects"].get(f"minecraft/lang/{language}.json")
        if asset is None:
            continue
        digest = asset["hash"]
        url = f"{generator.DEFAULT_ASSETS}{digest[:2]}/{digest}"
        path = directory / f"{language}.json"
        download(url, path, digest)
        files[language] = path
        urls[url] = str(path)
    return directory, files, urls


def compare_modes(directory, files, urls):
    entry = json.loads((directory / "version_manifest.json").read_bytes())["versions"][0]
    asset = json.loads((directory / "version.json").read_bytes())["assetIndex"]["url"]
    options = ["--version", entry["id"], "--asset", asset, "--asset-note", entry.get("time", entry.get("releaseTime", ""))]
    comparisons = 0
    for flavor, languages in (("zh", list(ZH_LANGUAGES)), ("lzh", ["en_us", "lzh"])):
        if not all(language in files for language in languages):
            print(f"  skip {flavor} comparison: this version lacks one of {languages}", flush=True)
            continue
        arguments = generator.make_parser().parse_args(["manual", *options, *[str(files[code]) for code in languages]])
        base, columns, metadata = generator.manual_data(arguments)
        expected = generator.render(base, columns, metadata).encode("utf-8")
        actual = automatic_from_files(directory / "version_manifest.json", languages, urls)
        if actual != expected:
            raise AssertionError(f"{directory.name} {flavor}: auto and manual generated files differ")
        print(f"  {flavor} auto/manual byte-identical ({len(actual):,} bytes), SHA-256 {hashlib.sha256(actual).hexdigest()}", flush=True)
        comparisons += 1
    return comparisons


def check_unicode(directory, files, urls):
    languages = [code for code in RARE_LANGUAGES if code in files]
    order = ["en_us", *languages]
    arguments = generator.make_parser().parse_args(["manual", *[str(files[code]) for code in order]])
    base, columns, metadata = generator.manual_data(arguments)
    outputs = {
        "manual": generator.render(base, columns, metadata).encode("utf-8"),
        "auto": automatic_from_files(directory / "version_manifest.json", order, urls),
    }
    data = {code: json.loads(files[code].read_bytes()) for code in order}
    english = data["en_us"]
    for mode, output in outputs.items():
        (directory / f"rare-languages-{mode}.lua").write_bytes(output)
        with LuaTable(output) as table:
            if mode == "auto" and table.field("_meta.version") != directory.name:
                raise AssertionError(f"wrong auto version for {directory.name}")
            for key, fallback in english.items():
                expected = [data[code].get(key, fallback) for code in order]
                if table.row(key, len(order)) != expected:
                    raise AssertionError(f"{mode} Lua round-trip failed for {directory.name} {key!r}")
        print(f"  {mode} Lua 5.1 round-trip: {len(english):,} keys × {len(order)} columns, all exact", flush=True)
    for language in languages:
        characters = collections.Counter("".join(data[language].values()))
        supplementary = sum(count for char, count in characters.items() if ord(char) > 0xFFFF)
        combining = sum(count for char, count in characters.items() if unicodedata.combining(char))
        print(f"    {language}: {supplementary:,} supplementary-plane characters, {combining:,} combining characters", flush=True)
    return len(english) * len(order) * len(outputs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, help="reuse downloaded files in this directory (default: disposable temporary directory)")
    parser.add_argument("--manifest", type=Path, help="use a saved official manifest instead of downloading it")
    parser.add_argument("--versions", nargs="+", default=["latest", "1.21.8", "1.13"], help="version IDs to check; latest is the first manifest entry")
    arguments = parser.parse_args()
    with LuaTable(b"return {}"):
        pass
    with tempfile.TemporaryDirectory(prefix="nameprovider-official-") as temporary:
        cache = arguments.cache or Path(temporary)
        cache.mkdir(parents=True, exist_ok=True)
        manifest = json.loads(arguments.manifest.read_bytes() if arguments.manifest else download(generator.DEFAULT_MANIFEST, cache / "manifest.json"))
        versions = list(dict.fromkeys(manifest["versions"][0]["id"] if value == "latest" else value for value in arguments.versions))
        comparisons = 0
        cells = 0
        for version in versions:
            print(f"Checking {version}", flush=True)
            directory, files, urls = prepare(cache, manifest, version)
            comparisons += compare_modes(directory, files, urls)
            cells += check_unicode(directory, files, urls)
        print(f"PASS: {comparisons} auto/manual comparisons and {cells:,} exact Lua string round-trips", flush=True)


if __name__ == "__main__":
    try:
        main()
    except LuaRuntimeError as error:
        sys.exit(str(error))
