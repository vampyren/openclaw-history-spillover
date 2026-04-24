import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {
  CHAT_HISTORY_OMITTED_MARKER,
  CHAT_HISTORY_SPILLED_MARKER,
  CHAT_HISTORY_SPILLOVER_DIRNAME,
  buildOversizedHistoryOmittedPlaceholder,
  buildOversizedHistorySpilloverPlaceholder,
  extractChatHistoryPreview,
  jsonUtf8Bytes,
  replaceOversizedChatHistoryMessages,
  safeSerializeForSpillover
} from '../src/spillover.js';

function makeTempDir(t) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'spillover-'));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  return dir;
}

test('jsonUtf8Bytes returns 0 for undefined', () => {
  assert.equal(jsonUtf8Bytes(undefined), 0);
});

test('safeSerializeForSpillover serializes basic values', () => {
  const out = safeSerializeForSpillover({ a: 1 });
  assert.match(out, /"a": 1/);
});

test('extractChatHistoryPreview truncates on code points', () => {
  const out = extractChatHistoryPreview('😀😀😀', 2);
  assert.equal(out, '😀😀\n…[truncated preview]');
});

test('buildOversizedHistorySpilloverPlaceholder writes spillover file with safe perms', (t) => {
  const tmp = makeTempDir(t);
  const transcriptPath = path.join(tmp, 'session.jsonl');
  fs.writeFileSync(transcriptPath, '');
  const message = { role: 'assistant', timestamp: 123, content: [{ type: 'text', text: 'x'.repeat(5000) }] };
  const placeholder = buildOversizedHistorySpilloverPlaceholder(message, {
    transcriptPath,
    sessionId: '../agent:main:main',
    messageId: '42',
    now: Date.UTC(2026, 3, 23, 15, 0, 0)
  });
  assert.equal(placeholder.role, 'assistant');
  assert.equal(placeholder.timestamp, 123);
  assert.match(placeholder.content[0].text, /\[chat\.history spilled: message too large\]/);
  assert.ok(placeholder.__openclaw.spilloverFile);
  assert.ok(fs.existsSync(placeholder.__openclaw.spilloverFile));
  assert.match(placeholder.__openclaw.spilloverFile, new RegExp(`${CHAT_HISTORY_SPILLOVER_DIRNAME}.+_agent_main_main-42\\.json$`));
  const payload = JSON.parse(fs.readFileSync(placeholder.__openclaw.spilloverFile, 'utf8'));
  assert.equal(payload.sessionId, '../agent:main:main');
  assert.equal(payload.byteLength > 0, true);
  const stat = fs.statSync(placeholder.__openclaw.spilloverFile);
  assert.equal(stat.mode & 0o777, 0o600);
});

test('buildOversizedHistorySpilloverPlaceholder falls back to omitted placeholder on write failure', () => {
  const message = { role: 'assistant', content: [{ type: 'text', text: 'x'.repeat(5000) }] };
  const fakeFs = {
    mkdirSync() { throw new Error('nope'); }
  };
  const placeholder = buildOversizedHistorySpilloverPlaceholder(message, { fsModule: fakeFs, now: 7 });
  assert.equal(placeholder.content[0].text, CHAT_HISTORY_OMITTED_MARKER);
  assert.equal(placeholder.timestamp, 7);
  assert.equal(placeholder.__openclaw.spilloverFile, undefined);
});

test('replaceOversizedChatHistoryMessages validates maxSingleMessageBytes', () => {
  assert.throws(() => replaceOversizedChatHistoryMessages({ messages: [], maxSingleMessageBytes: undefined }), /maxSingleMessageBytes/);
});

test('replaceOversizedChatHistoryMessages only replaces oversized items and keeps boundary item', (t) => {
  const tmp = makeTempDir(t);
  const transcriptPath = path.join(tmp, 'session.jsonl');
  fs.writeFileSync(transcriptPath, '');
  const small = { role: 'assistant', content: [{ type: 'text', text: 'ok' }] };
  const exact = { role: 'assistant', content: [{ type: 'text', text: '1234567890' }] };
  const exactBytes = jsonUtf8Bytes(exact);
  const big = { role: 'assistant', content: [{ type: 'text', text: 'z'.repeat(6000) }] };
  const res = replaceOversizedChatHistoryMessages({
    messages: [small, undefined, exact, big],
    maxSingleMessageBytes: exactBytes,
    transcriptPath,
    sessionId: 'abc',
    now: 99
  });
  assert.equal(res.replacedCount, 1);
  assert.equal(res.messages[0], small);
  assert.equal(res.messages[1], undefined);
  assert.equal(res.messages[2], exact);
  assert.match(res.messages[3].content[0].text, new RegExp(CHAT_HISTORY_SPILLED_MARKER.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
  assert.equal(res.messages[3].__openclaw.originalBytes > exactBytes, true);
});

test('buildOversizedHistoryOmittedPlaceholder preserves now fallback', () => {
  const placeholder = buildOversizedHistoryOmittedPlaceholder(undefined, { now: 321 });
  assert.equal(placeholder.timestamp, 321);
  assert.equal(placeholder.content[0].text, CHAT_HISTORY_OMITTED_MARKER);
});
