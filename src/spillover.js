import fs from 'node:fs';
import path from 'node:path';

export const CHAT_HISTORY_SPILLOVER_DIRNAME = 'history-oversize';
export const CHAT_HISTORY_PREVIEW_MAX_CHARS = 1200;
export const CHAT_HISTORY_SPILLED_MARKER = '[chat.history spilled: message too large]';
export const CHAT_HISTORY_OMITTED_MARKER = '[chat.history omitted: message too large]';

export function jsonUtf8Bytes(value) {
  const serialized = JSON.stringify(value);
  return serialized === undefined ? 0 : Buffer.byteLength(serialized, 'utf8');
}

export function safeSerializeForSpillover(value) {
  try {
    return JSON.stringify(value, null, 2);
  } catch (err) {
    return JSON.stringify({ error: String(err), fallback: String(value) }, null, 2);
  }
}

export function extractChatHistoryPreview(message, maxChars = CHAT_HISTORY_PREVIEW_MAX_CHARS) {
  try {
    const raw = typeof message === 'string' ? message : safeSerializeForSpillover(message);
    const chars = Array.from(raw);
    return chars.length > maxChars ? `${chars.slice(0, maxChars).join('')}\n…[truncated preview]` : raw;
  } catch {
    return '[preview unavailable]';
  }
}

export function sanitizeIdPart(value, fallback = 'item') {
  const out = String(value ?? fallback).replace(/[^a-zA-Z0-9._-]+/g, '_');
  return out || fallback;
}

export function ensureChatHistorySpilloverDir(baseDir, options = {}) {
  const fsModule = options.fsModule ?? fs;
  const pathModule = options.pathModule ?? path;
  const dir = pathModule.join(baseDir, CHAT_HISTORY_SPILLOVER_DIRNAME);
  fsModule.mkdirSync(dir, { recursive: true, mode: 0o700 });
  return dir;
}

export function buildOversizedHistoryOmittedPlaceholder(message, options = {}) {
  const now = options.now ?? Date.now();
  return {
    role: message && typeof message === 'object' && typeof message.role === 'string' ? message.role : 'assistant',
    timestamp: message && typeof message === 'object' && typeof message.timestamp === 'number' ? message.timestamp : now,
    content: [{
      type: 'text',
      text: CHAT_HISTORY_OMITTED_MARKER
    }],
    __openclaw: {
      truncated: true,
      reason: 'oversized'
    }
  };
}

export function persistOversizedHistoryMessage(message, options = {}) {
  const fsModule = options.fsModule ?? fs;
  const pathModule = options.pathModule ?? path;
  const now = options.now ?? Date.now();
  const transcriptPath = options.transcriptPath;
  const baseDir = transcriptPath ? pathModule.dirname(transcriptPath) : pathModule.join(options.cwd ?? process.cwd(), '.openclaw-history');
  const dir = ensureChatHistorySpilloverDir(baseDir, { fsModule, pathModule });
  const ts = new Date(now).toISOString().replace(/[:.]/g, '-');
  const sessionPart = sanitizeIdPart(options.sessionId || 'session', 'session');
  const idPart = sanitizeIdPart(options.messageId || now, 'message');
  const filePath = pathModule.join(dir, `${ts}-${sessionPart}-${idPart}.json`);
  const payload = {
    createdAt: new Date(now).toISOString(),
    sessionId: options.sessionId ?? null,
    transcriptPath: transcriptPath ?? null,
    byteLength: jsonUtf8Bytes(message),
    message
  };
  const tmpPath = `${filePath}.tmp-${process.pid}-${now}`;
  fsModule.writeFileSync(tmpPath, safeSerializeForSpillover(payload), { encoding: 'utf8', mode: 0o600 });
  fsModule.renameSync(tmpPath, filePath);
  return filePath;
}

export function buildOversizedHistorySpilloverPlaceholder(message, options = {}) {
  const now = options.now ?? Date.now();
  const preview = extractChatHistoryPreview(message, options.previewMaxChars);
  const byteLength = jsonUtf8Bytes(message);
  let filePath;
  try {
    filePath = persistOversizedHistoryMessage(message, options);
  } catch {
    return buildOversizedHistoryOmittedPlaceholder(message, { now });
  }
  return {
    role: message && typeof message === 'object' && typeof message.role === 'string' ? message.role : 'assistant',
    timestamp: message && typeof message === 'object' && typeof message.timestamp === 'number' ? message.timestamp : now,
    content: [{
      type: 'text',
      text: `${CHAT_HISTORY_SPILLED_MARKER}\nbytes=${byteLength}${filePath ? `\nfile=${filePath}` : ''}\npreview:\n${preview}`
    }],
    __openclaw: {
      truncated: true,
      reason: 'oversized',
      spilloverFile: filePath || undefined,
      originalBytes: byteLength
    }
  };
}

export function replaceOversizedChatHistoryMessages({ messages, maxSingleMessageBytes, transcriptPath, sessionId, now, fsModule, pathModule, cwd } = {}) {
  if (typeof maxSingleMessageBytes !== 'number' || !Number.isFinite(maxSingleMessageBytes) || maxSingleMessageBytes < 0) {
    throw new TypeError('maxSingleMessageBytes must be a finite non-negative number');
  }
  if (!Array.isArray(messages) || messages.length === 0) return { messages: messages ?? [], replacedCount: 0 };
  let replacedCount = 0;
  const next = messages.map((message, index) => {
    if (jsonUtf8Bytes(message) <= maxSingleMessageBytes) return message;
    replacedCount += 1;
    return buildOversizedHistorySpilloverPlaceholder(message, {
      transcriptPath,
      sessionId,
      messageId: index,
      now,
      fsModule,
      pathModule,
      cwd
    });
  });
  return { messages: replacedCount > 0 ? next : messages, replacedCount };
}
