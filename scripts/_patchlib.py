from __future__ import annotations

import difflib
import glob
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

OPENCLAW_ROOT = Path('/usr/lib/node_modules/openclaw')
DIST_DIR = OPENCLAW_ROOT / 'dist'
STATE_DIR = OPENCLAW_ROOT / '.openclaw-history-spillover'
BACKUPS_DIR = STATE_DIR / 'backups'
MANIFEST_PATH = STATE_DIR / 'installed.json'
PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_JSON_PATH = PROJECT_ROOT / 'package.json'
SOURCE_PATH = PROJECT_ROOT / 'src' / 'spillover.js'

PATCH_MARKER = 'const CHAT_HISTORY_SPILLOVER_DIRNAME = "history-oversize";'
PATCH_MARKER_ALT = "const CHAT_HISTORY_SPILLOVER_DIRNAME = 'history-oversize';"

INJECTED_BLOCK = '''const CHAT_HISTORY_SPILLOVER_DIRNAME = "history-oversize";
const CHAT_HISTORY_PREVIEW_MAX_CHARS = 1200;
function serializeChatHistoryMessageForBytes(value) {
\ttry {
\t\tconst text = JSON.stringify(value);
\t\treturn {
\t\t\ttext,
\t\t\tbyteLength: text === void 0 ? 0 : Buffer.byteLength(text, "utf8")
\t\t};
\t} catch (err) {
\t\tconst fallback = JSON.stringify({ error: formatForLog(err), fallback: String(value) });
\t\treturn {
\t\t\ttext: fallback,
\t\t\tbyteLength: Buffer.byteLength(fallback, "utf8")
\t\t};
\t}
}
function safeSerializeForSpillover(value) {
\ttry {
\t\treturn JSON.stringify(value, null, 2);
\t} catch (err) {
\t\treturn JSON.stringify({ error: formatForLog(err), fallback: String(value) }, null, 2);
\t}
}
function extractChatHistoryPreview(message, maxChars = CHAT_HISTORY_PREVIEW_MAX_CHARS) {
\ttry {
\t\tconst raw = typeof message === "string" ? message : safeSerializeForSpillover(message);
\t\tconst chars = Array.from(raw);
\t\treturn chars.length > maxChars ? `${chars.slice(0, maxChars).join("")}\n…[truncated preview]` : raw;
\t} catch {
\t\treturn "[preview unavailable]";
\t}
}
function sanitizeHistorySpilloverIdPart(value, fallback = "item") {
\tconst out = String(value ?? fallback).replace(/[^a-zA-Z0-9._-]+/g, "_");
\treturn out || fallback;
}
function ensureChatHistorySpilloverDir(baseDir) {
\tconst dir = path.join(baseDir, CHAT_HISTORY_SPILLOVER_DIRNAME);
\tfs.mkdirSync(dir, { recursive: true, mode: 448 });
\treturn dir;
}
function buildOversizedHistoryOmittedPlaceholder(message, options) {
\tconst now = options?.now ?? Date.now();
\treturn {
\t\trole: message && typeof message === "object" && typeof message.role === "string" ? message.role : "assistant",
\t\ttimestamp: message && typeof message === "object" && typeof message.timestamp === "number" ? message.timestamp : now,
\t\tcontent: [{
\t\t\ttype: "text",
\t\t\ttext: CHAT_HISTORY_OVERSIZED_PLACEHOLDER
\t\t}],
\t\t__openclaw: {
\t\t\ttruncated: true,
\t\t\treason: "oversized"
\t\t}
\t};
}
function persistOversizedHistoryMessage(message, options) {
\tconst now = options?.now ?? Date.now();
\tconst transcriptPath = options?.transcriptPath;
\tconst baseDir = transcriptPath ? path.dirname(transcriptPath) : path.join(process.cwd(), ".openclaw-history");
\tconst dir = ensureChatHistorySpilloverDir(baseDir);
\tconst ts = new Date(now).toISOString().replace(/[:.]/g, "-");
\tconst sessionPart = sanitizeHistorySpilloverIdPart(options?.sessionId || "session", "session");
\tconst idPart = sanitizeHistorySpilloverIdPart(options?.messageId || now, "message");
\tconst filePath = path.join(dir, `${ts}-${sessionPart}-${idPart}.json`);
\tconst payload = {
\t\tcreatedAt: new Date(now).toISOString(),
\t\tsessionId: options?.sessionId ?? null,
\t\ttranscriptPath: transcriptPath || null,
\t\tbyteLength: serializeChatHistoryMessageForBytes(message).byteLength,
\t\tmessage
\t};
\tconst tmpPath = `${filePath}.tmp-${process.pid}-${now}`;
\tfs.writeFileSync(tmpPath, safeSerializeForSpillover(payload), { encoding: "utf8", mode: 384 });
\tfs.renameSync(tmpPath, filePath);
\treturn filePath;
}
function buildOversizedHistorySpilloverPlaceholder(message, options) {
\tconst now = options?.now ?? Date.now();
\tconst serialized = serializeChatHistoryMessageForBytes(message);
\tconst preview = extractChatHistoryPreview(message, options?.previewMaxChars);
\tlet filePath;
\ttry {
\t\tfilePath = persistOversizedHistoryMessage(message, options);
\t} catch {
\t\treturn buildOversizedHistoryOmittedPlaceholder(message, { now });
\t}
\treturn {
\t\trole: message && typeof message === "object" && typeof message.role === "string" ? message.role : "assistant",
\t\ttimestamp: message && typeof message === "object" && typeof message.timestamp === "number" ? message.timestamp : now,
\t\tcontent: [{
\t\t\ttype: "text",
\t\t\ttext: `[chat.history spilled: message too large]\nbytes=${serialized.byteLength}${filePath ? `\nfile=${filePath}` : ""}\npreview:\n${preview}`
\t\t}],
\t\t__openclaw: {
\t\t\ttruncated: true,
\t\t\treason: "oversized",
\t\t\tspilloverFile: filePath || void 0,
\t\t\toriginalBytes: serialized.byteLength
\t\t}
\t};
}
'''

PLACEHOLDER_WRAPPER = '''function buildOversizedHistoryPlaceholder(message, options) {
\treturn buildOversizedHistorySpilloverPlaceholder(message, options);
}
'''

REPLACE_OVERSIZED_FUNCTION = '''function replaceOversizedChatHistoryMessages(params) {
\tconst { messages, maxSingleMessageBytes, transcriptPath, sessionId, logGateway } = params;
\tif (typeof maxSingleMessageBytes !== "number" || !Number.isFinite(maxSingleMessageBytes) || maxSingleMessageBytes < 0) throw new TypeError("maxSingleMessageBytes must be a finite non-negative number");
\tif (!Array.isArray(messages) || messages.length === 0) return {
\t\tmessages: messages ?? [],
\t\treplacedCount: 0
\t};
\tlet replacedCount = 0;
\tconst next = messages.map((message, index) => {
\t\tif (serializeChatHistoryMessageForBytes(message).byteLength <= maxSingleMessageBytes) return message;
\t\treplacedCount += 1;
\t\tconst replacement = buildOversizedHistoryPlaceholder(message, { transcriptPath, sessionId, messageId: index, logGateway });
\t\tif (replacement?.__openclaw?.spilloverFile || replacement?.content?.[0]?.text === CHAT_HISTORY_OVERSIZED_PLACEHOLDER) return replacement;
\t\treturn buildOversizedHistoryOmittedPlaceholder(message);
\t});
\treturn {
\t\tmessages: replacedCount > 0 ? next : messages,
\t\treplacedCount
\t};
}
'''

HISTORY_CALL_BLOCK = '''\t\tconst maxHistoryBytes = getMaxChatHistoryMessagesBytes();
\t\tconst transcriptPath = resolveTranscriptPath({
\t\t\tsessionId,
\t\t\tstorePath,
\t\t\tsessionFile: entry?.sessionFile,
\t\t\tagentId: entry?.agentId
\t\t});
\t\tconst replaced = replaceOversizedChatHistoryMessages({
\t\t\tmessages: normalized,
\t\t\tmaxSingleMessageBytes: Math.min(CHAT_HISTORY_MAX_SINGLE_MESSAGE_BYTES, maxHistoryBytes),
\t\t\ttranscriptPath,
\t\t\tsessionId,
\t\t\tlogGateway: context.logGateway
\t\t});
\t\tconst capped = capArrayByJsonBytes(replaced.messages, maxHistoryBytes).items;'''


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def read_package_version() -> str:
    return json.loads(PACKAGE_JSON_PATH.read_text())['version']


def read_source_sha() -> str:
    return sha256_text(SOURCE_PATH.read_text())


def load_manifest() -> Optional[dict]:
    if not MANIFEST_PATH.exists():
        return None
    return json.loads(MANIFEST_PATH.read_text())


def save_manifest(data: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(data, indent=2) + '\n')
    os.chmod(MANIFEST_PATH, 0o600)


def openclaw_version() -> str:
    package_json = OPENCLAW_ROOT / 'package.json'
    if not package_json.exists():
        return 'unknown'
    return json.loads(package_json.read_text()).get('version', 'unknown')


def find_patch_target() -> Path:
    candidates = sorted(glob.glob(str(DIST_DIR / 'chat-*.js')))
    matches = []
    for raw in candidates:
        p = Path(raw)
        text = p.read_text()
        if 'replaceOversizedChatHistoryMessages' in text and 'buildOversizedHistoryPlaceholder' in text and 'CHAT_HISTORY_OVERSIZED_PLACEHOLDER' in text:
            matches.append(p)
    if len(matches) != 1:
        raise SystemExit(f'expected 1 patch target, found {len(matches)}: {matches}')
    return matches[0]


def replace_span(text: str, start_marker: str, end_marker: str, replacement: str, label: str, include_end: bool = False) -> str:
    start = text.find(start_marker)
    if start == -1:
        raise SystemExit(f'failed to find start marker for {label}')
    end = text.find(end_marker, start)
    if end == -1:
        raise SystemExit(f'failed to find end marker for {label}')
    if include_end:
        end += len(end_marker)
    return text[:start] + replacement + text[end:]


def render_patched_text(original: str) -> str:
    text = replace_span(
        original,
        'let chatHistoryPlaceholderEmitCount = 0;\n',
        'const CHANNEL_AGNOSTIC_SESSION_SCOPES = new Set([',
        'let chatHistoryPlaceholderEmitCount = 0;\n' + INJECTED_BLOCK + '\n',
        'helper injection'
    )
    text = replace_span(
        text,
        'function buildOversizedHistoryPlaceholder(',
        'function replaceOversizedChatHistoryMessages(params) {',
        PLACEHOLDER_WRAPPER,
        'placeholder wrapper'
    )
    text = replace_span(
        text,
        'function replaceOversizedChatHistoryMessages(params) {',
        'function enforceChatHistoryFinalBudget(params) {',
        REPLACE_OVERSIZED_FUNCTION,
        'replace oversized function'
    )
    text = replace_span(
        text,
        '\t\tconst maxHistoryBytes = getMaxChatHistoryMessagesBytes();',
        '\t\tconst capped = capArrayByJsonBytes(replaced.messages, maxHistoryBytes).items;',
        HISTORY_CALL_BLOCK,
        'history call block',
        include_end=True
    )
    if PATCH_MARKER not in text or 'spilloverFile: filePath || void 0' not in text:
        raise SystemExit('patched text missing expected markers')
    return text


def looks_patched(text: str) -> bool:
    return PATCH_MARKER in text or PATCH_MARKER_ALT in text


def backup_path_for_sha(sha: str) -> Path:
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    return BACKUPS_DIR / f'{sha}.js'


def write_backup_if_missing(target_text: str) -> Path:
    sha = sha256_text(target_text)
    backup_path = backup_path_for_sha(sha)
    if not backup_path.exists():
        backup_path.write_text(target_text)
        os.chmod(backup_path, 0o600)
    return backup_path


def unified_diff(before: str, after: str, fromfile: str, tofile: str) -> str:
    return ''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True), fromfile=fromfile, tofile=tofile))


@dataclass
class VerificationResult:
    status: str
    target: Path
    message: str
    manifest: Optional[dict]


def verify_install() -> VerificationResult:
    target = find_patch_target()
    current_text = target.read_text()
    current_sha = sha256_text(current_text)
    manifest = load_manifest()
    if manifest is None:
        if looks_patched(current_text):
            return VerificationResult('patched-unmanaged', target, 'target is patched but no install manifest exists', None)
        return VerificationResult('unpatched', target, 'target is not patched', None)
    if str(target) != manifest.get('targetPath'):
        return VerificationResult('moved-target', target, 'resolved target does not match manifest target path', manifest)
    if current_sha == manifest.get('postSha256'):
        return VerificationResult('patched', target, 'installed patch matches manifest', manifest)
    if current_sha == manifest.get('preSha256'):
        return VerificationResult('reverted', target, 'target matches recorded pre-patch content', manifest)
    if looks_patched(current_text):
        return VerificationResult('patched-drifted', target, 'target still looks patched but hash differs from manifest', manifest)
    return VerificationResult('changed', target, 'target differs from both pre/post manifest hashes', manifest)
