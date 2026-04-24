"""Tests for the Python patch pipeline.

These tests use a synthetic bundle fixture that contains all the anchor strings
and bundle-internal symbols render_patched_text() expects. That way we can
exercise the pipeline without needing a real OpenClaw install.

Run from the project root:
    python3 -m unittest tests.test_patchlib
"""
from __future__ import annotations

import os
import sys
import shutil
import tempfile
import unittest
from pathlib import Path

# Make scripts/ importable
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / 'scripts'))

import _patchlib  # noqa: E402
from _patchlib import (  # noqa: E402
    PATCH_MARKER,
    REQUIRED_BUNDLE_SYMBOLS,
    find_patch_target,
    looks_patched,
    missing_bundle_symbols,
    render_patched_text,
    sha256_text,
    syntax_check_js,
)


# A synthetic pre-patch openclaw bundle. Contains every anchor string that
# render_patched_text() looks for and every bundle-internal symbol the injected
# code references. Kept deliberately minimal and valid JS.
SYNTHETIC_BUNDLE = '''// synthetic openclaw bundle for tests
const fs = require("fs");
const path = require("path");
const CHAT_HISTORY_OVERSIZED_PLACEHOLDER = "[chat.history omitted: message too large]";
const CHAT_HISTORY_MAX_SINGLE_MESSAGE_BYTES = 128 * 1024;
function formatForLog(err) { return String(err); }
function resolveTranscriptPath(params) { return params.sessionFile; }
function getMaxChatHistoryMessagesBytes() { return 1024 * 1024; }
function capArrayByJsonBytes(items, max) { return { items }; }
let chatHistoryPlaceholderEmitCount = 0;
const CHANNEL_AGNOSTIC_SESSION_SCOPES = new Set([
\t"scope1",
\t"scope2"
]);
function buildOversizedHistoryPlaceholder(message, options) {
\treturn {
\t\trole: "assistant",
\t\tcontent: [{ type: "text", text: CHAT_HISTORY_OVERSIZED_PLACEHOLDER }]
\t};
}
function replaceOversizedChatHistoryMessages(params) {
\tconst { messages } = params;
\treturn { messages: messages ?? [], replacedCount: 0 };
}
function enforceChatHistoryFinalBudget(params) {
\treturn params;
}
function processChatHistory(entry, context, storePath, sessionId) {
\tconst normalized = entry.messages;
\t{
\t\tconst maxHistoryBytes = getMaxChatHistoryMessagesBytes();
\t\tconst replaced = replaceOversizedChatHistoryMessages({
\t\t\tmessages: normalized,
\t\t\tmaxSingleMessageBytes: Math.min(CHAT_HISTORY_MAX_SINGLE_MESSAGE_BYTES, maxHistoryBytes)
\t\t});
\t\tconst capped = capArrayByJsonBytes(replaced.messages, maxHistoryBytes).items;
\t\treturn capped;
\t}
}
module.exports = { processChatHistory };
'''


class FindPatchTargetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix='patchlib-'))

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_finds_matching_bundle(self) -> None:
        good = self.tmp / 'chat-abc123.js'
        good.write_text(SYNTHETIC_BUNDLE)
        # decoy without the required markers
        (self.tmp / 'chat-other.js').write_text('// not a patch target\n')
        result = find_patch_target(dist_dir=self.tmp)
        self.assertEqual(result, good)

    def test_rejects_ambiguous(self) -> None:
        (self.tmp / 'chat-one.js').write_text(SYNTHETIC_BUNDLE)
        (self.tmp / 'chat-two.js').write_text(SYNTHETIC_BUNDLE)
        with self.assertRaises(SystemExit):
            find_patch_target(dist_dir=self.tmp)

    def test_rejects_no_matches(self) -> None:
        (self.tmp / 'chat-nope.js').write_text('// no markers here\n')
        with self.assertRaises(SystemExit):
            find_patch_target(dist_dir=self.tmp)


class RenderPatchedTextTests(unittest.TestCase):
    def test_contains_marker_and_no_double_inject(self) -> None:
        out = render_patched_text(SYNTHETIC_BUNDLE)
        self.assertIn(PATCH_MARKER, out)
        # The marker should appear exactly once (no accidental duplication).
        self.assertEqual(out.count(PATCH_MARKER), 1)

    def test_is_idempotent(self) -> None:
        once = render_patched_text(SYNTHETIC_BUNDLE)
        twice = render_patched_text(once)
        self.assertEqual(once, twice)
        # SHAs must match too
        self.assertEqual(sha256_text(once), sha256_text(twice))

    def test_preserves_bundle_symbols(self) -> None:
        out = render_patched_text(SYNTHETIC_BUNDLE)
        missing = missing_bundle_symbols(out)
        self.assertEqual(missing, [], f'patched output missing symbols: {missing}')

    def test_fails_when_anchor_marker_missing(self) -> None:
        bad = SYNTHETIC_BUNDLE.replace('let chatHistoryPlaceholderEmitCount = 0;', '// removed')
        with self.assertRaises(SystemExit):
            render_patched_text(bad)

    def test_fails_when_required_symbol_missing(self) -> None:
        # Remove `formatForLog` — the anchors for render_patched_text's span
        # replacements are still present, but a bundle symbol the injected
        # code depends on is gone. Must fail before touching the file.
        bad = SYNTHETIC_BUNDLE.replace('function formatForLog(err) { return String(err); }\n', '')
        with self.assertRaises(SystemExit) as cm:
            render_patched_text(bad)
        self.assertIn('formatForLog', str(cm.exception))

    def test_output_contains_expected_helpers(self) -> None:
        out = render_patched_text(SYNTHETIC_BUNDLE)
        for fn in ('buildOversizedHistorySpilloverPlaceholder',
                   'persistOversizedHistoryMessage',
                   'ensureChatHistorySpilloverDir',
                   'serializeChatHistoryMessageForBytes'):
            self.assertIn(fn, out, f'patched output should contain {fn}')

    def test_output_is_valid_js(self) -> None:
        out = render_patched_text(SYNTHETIC_BUNDLE)
        # syntax_check_js is a no-op if node is missing, which is fine.
        # When node IS present, this catches emit bugs like unterminated strings.
        syntax_check_js(out)


class LooksPatchedTests(unittest.TestCase):
    def test_unpatched_bundle(self) -> None:
        self.assertFalse(looks_patched(SYNTHETIC_BUNDLE))

    def test_patched_bundle(self) -> None:
        patched = render_patched_text(SYNTHETIC_BUNDLE)
        self.assertTrue(looks_patched(patched))


class MissingBundleSymbolsTests(unittest.TestCase):
    def test_full_bundle_is_complete(self) -> None:
        self.assertEqual(missing_bundle_symbols(SYNTHETIC_BUNDLE), [])

    def test_reports_each_missing(self) -> None:
        # Strip all required symbols out; every one should be reported.
        stripped = SYNTHETIC_BUNDLE
        for sym in REQUIRED_BUNDLE_SYMBOLS:
            stripped = stripped.replace(sym, 'REMOVED_' + sym[::-1])
        missing = missing_bundle_symbols(stripped)
        self.assertCountEqual(missing, REQUIRED_BUNDLE_SYMBOLS)


class Sha256Tests(unittest.TestCase):
    def test_stable_and_hex(self) -> None:
        a = sha256_text('hello')
        b = sha256_text('hello')
        self.assertEqual(a, b)
        self.assertEqual(len(a), 64)
        self.assertTrue(all(c in '0123456789abcdef' for c in a))


class StateDirResolutionTests(unittest.TestCase):
    """_resolve_state_dir is called at import time, but we can still test the
    env-override pathway by re-invoking it with a patched environment."""

    def test_env_override_wins(self) -> None:
        old = os.environ.get('OPENCLAW_HISTORY_SPILLOVER_STATE_DIR')
        try:
            os.environ['OPENCLAW_HISTORY_SPILLOVER_STATE_DIR'] = '/tmp/explicit-override'
            resolved = _patchlib._resolve_state_dir()
            self.assertEqual(str(resolved), '/tmp/explicit-override')
        finally:
            if old is None:
                del os.environ['OPENCLAW_HISTORY_SPILLOVER_STATE_DIR']
            else:
                os.environ['OPENCLAW_HISTORY_SPILLOVER_STATE_DIR'] = old


if __name__ == '__main__':
    unittest.main()
