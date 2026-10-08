-- version: snapshot-test
-- asset: assets.json (2026-10-06T13:00:46+00:00)
return {
	[ '_meta.version' ] = "snapshot-test",
	[ 'item.test2' ] = { "Two", "兩" },
	[ 'item.test10' ] = { "Ten", "拾" },
	[ 'only.english' ] = { "Fallback", "Fallback" },
	[ 'quote.test' ] = { "\"quote\" \\ path\nnext", "曰" },
}
