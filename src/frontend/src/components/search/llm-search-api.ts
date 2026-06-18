/**
 * Shared API functions for LLM Search / Copilot features.
 */

import type {
  ChatResponse,
  LLMSearchStatus,
  SessionSummary,
} from '@/types/llm-search';

export async function fetchLLMStatus(): Promise<LLMSearchStatus> {
  const response = await fetch('/api/llm-search/status');
  if (!response.ok) throw new Error('Failed to fetch LLM status');
  return response.json();
}

export async function fetchSessions(): Promise<SessionSummary[]> {
  const response = await fetch('/api/llm-search/sessions');
  if (!response.ok) throw new Error('Failed to fetch sessions');
  return response.json();
}

export async function sendMessage(content: string, sessionId?: string, debug?: boolean): Promise<ChatResponse> {
  const response = await fetch('/api/llm-search/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content, session_id: sessionId, debug: debug || false }),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Chat request failed' }));
    throw new Error(error.detail || 'Chat request failed');
  }
  return response.json();
}

export interface ContractStreamCallbacks {
  onSession?: (sessionId: string) => void;
  onStage?: (stage: { step: string; status: 'start' | 'done'; [k: string]: unknown }) => void;
  onToken?: (delta: string) => void;
  onResult?: (r: {
    contract_id: string | null;
    contract: unknown;
    llm_model?: string;
    duration_seconds?: number;
    warnings?: string[];
  }) => void;
  onExists?: (e: { message: string; existing: unknown[] }) => void;
  onError?: (message: string) => void;
}

/**
 * Stream a contract draft from POST /api/contract-generator/stream (SSE), invoking
 * callbacks as stage / token / result / exists / error events arrive. Parses SSE
 * frames off the fetch ReadableStream (native EventSource is GET-only and can't POST
 * a body). Resolves when the stream closes.
 */
export async function streamContractDraft(
  params: { catalog: string; schema: string; table: string; sampleSize?: number; force?: boolean; sessionId?: string },
  cb: ContractStreamCallbacks,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch('/api/contract-generator/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify({
      catalog: params.catalog,
      schema: params.schema,
      table: params.table,
      sample_size: params.sampleSize ?? 20,
      force: params.force ?? false,
      // Always send the field (empty string on the first turn) so the server
      // records the turn into llm_sessions: "" → create a session; a string
      // continues it. Omitting it entirely opts out of session recording.
      session_id: params.sessionId ?? '',
    }),
    signal,
  });
  if (!response.ok || !response.body) {
    const error = await response.json().catch(() => ({ detail: 'Contract draft stream failed' }));
    throw new Error(error.detail || 'Contract draft stream failed');
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  const dispatch = (frame: string) => {
    let eventType = 'message';
    const dataLines: string[] = [];
    for (const line of frame.split(/\r?\n/)) {
      if (line.startsWith('event:')) eventType = line.slice(6).trim();
      else if (line.startsWith('data:')) dataLines.push(line.slice(5).replace(/^ /, ''));
    }
    if (dataLines.length === 0) return; // keep-alive comment (": ping") or blank
    let payload: any;
    try {
      payload = JSON.parse(dataLines.join('\n'));
    } catch {
      return;
    }
    switch (eventType) {
      case 'session': if (payload.session_id) cb.onSession?.(payload.session_id); break;
      case 'stage': cb.onStage?.(payload); break;
      case 'token': cb.onToken?.(payload.delta ?? ''); break;
      case 'result': cb.onResult?.(payload); break;
      case 'exists': cb.onExists?.(payload); break;
      case 'error': cb.onError?.(payload.message ?? 'Unknown error'); break;
    }
  };

  // SSE frames are separated by a blank line. sse-starlette uses CRLF (\r\n\r\n);
  // tolerate LF (\n\n) too. Each frame has `event:` and `data:` lines.
  const FRAME_SEP = /\r?\n\r?\n/;
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let m: RegExpExecArray | null;
    while ((m = FRAME_SEP.exec(buffer)) !== null) {
      const frame = buffer.slice(0, m.index);
      buffer = buffer.slice(m.index + m[0].length);
      dispatch(frame);
    }
  }
  // Flush any trailing frame not terminated by a blank line before close.
  if (buffer.trim()) dispatch(buffer);
}

export async function deleteSession(sessionId: string): Promise<void> {
  const response = await fetch(`/api/llm-search/sessions/${sessionId}`, {
    method: 'DELETE',
  });
  if (!response.ok && response.status !== 204) {
    throw new Error('Failed to delete session');
  }
}
