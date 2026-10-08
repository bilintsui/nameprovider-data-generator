-- version: snapshot-test
-- asset: assets.json (2026-10-06T13:00:46+00:00)
return {
	[ '_meta.version' ] = "snapshot-test",
	[ 'item.test2' ] = { "Two", "二", "貳", "Two" },
	[ 'item.test10' ] = { "Ten", "十", "Ten", "拾" },
	[ 'only.english' ] = { "Fallback", "Fallback", "Fallback", "Fallback" },
	[ 'quote.test' ] = { "\"quote\" \\ path\nnext", "引号", "引號", "𥹉" },
}
