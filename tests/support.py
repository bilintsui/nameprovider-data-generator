"""Fixtures shared by offline tests and comparisons with official assets."""

import hashlib
import json
from pathlib import Path
import sys
from unittest.mock import patch
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import generator


def automatic_from_files(manifest, languages, urls):
    def open_source(self, source):
        return Path(urls.get(source, source)).open("rb")

    arguments = generator.make_parser().parse_args(["auto", "--manifest", str(manifest), *languages])
    with patch.object(generator.Downloader, "open", open_source):
        base, columns, metadata = generator.automatic_data(arguments)
    return generator.render(base, columns, metadata).encode("utf-8")


def make_fixture(directory, encoding="utf-8"):
    translations = {
        "en_us": {"item.test2": "Two", "item.test10": "Ten", "only.english": "Fallback", "quote.test": '"quote" \\ path\nnext'},
        "zh_cn": {"item.test2": "二", "item.test10": "十", "quote.test": "引号", "only.translation": "不输出"},
        "zh_tw": {"item.test2": "貳", "quote.test": "引號"},
        "zh_hk": {"item.test10": "拾", "quote.test": "𥹉"},
        "lzh": {"item.test2": "兩", "item.test10": "拾", "quote.test": "曰"},
    }
    objects = {}
    urls = {generator.DEFAULT_MANIFEST: str(directory / "manifest.json")}
    files = {}
    for language, values in translations.items():
        content = (json.dumps(values, ensure_ascii=False, indent=2) + "\n").encode(encoding)
        path = directory / f"{language}.json"
        path.write_bytes(content)
        files[language] = path
        if language != "en_us":
            digest = hashlib.sha1(content).hexdigest()
            objects[f"minecraft/lang/{language}.json"] = {"hash": digest, "size": len(content)}
            resource = directory / "objects" / digest[:2] / digest
            resource.parent.mkdir(parents=True, exist_ok=True)
            resource.write_bytes(content)
            urls[f"{generator.DEFAULT_ASSETS}{digest[:2]}/{digest}"] = str(resource)
    with ZipFile(directory / "client.jar", "w") as archive:
        archive.write(files["en_us"], "assets/minecraft/lang/en_us.json")
    (directory / "assets.json").write_text(json.dumps({"objects": objects}), encoding="utf-8")
    version = {"assetIndex": {"url": "assets.json"}, "downloads": {"client": {"url": "client.jar"}}}
    (directory / "version.json").write_text(json.dumps(version), encoding="utf-8")
    manifest = {
        "latest": {"release": "release-test", "snapshot": "snapshot-test"},
        "versions": [
            {"id": "snapshot-test", "url": "version.json", "time": "2026-10-06T13:00:46+00:00"},
            {"id": "release-test", "url": "version.json", "time": "2025-07-17T12:04:02+00:00"},
        ],
    }
    (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    for name in ("version.json", "assets.json", "client.jar"):
        urls[name] = str(directory / name)
    return files, translations, urls
