import { randomUUID } from 'node:crypto';

// A Mindcraft model provider backed by a session of CIEL, including its context.
// The host supplies a session capability; the model never chooses a memory owner.
export class CielModel {
  static prefix = 'ciel';

  constructor(_model, url, { token, fetch: transport = fetch } = {}) {
    if (!url || !token) throw new Error('CIEL URL and bound session token are required');
    this.url = url.replace(/\/$/, '');
    this.token = token;
    this.transport = transport;
    this.pending = new Map();
    this.reference = null;
    this.queue = null;
  }

  // Startup: register the fixed part of the execution prompt once, then let CIEL evaluate it.
  // Preparation failure only loses the speed-up; registration failure keeps full prompts.
  async prepareReference(reference, { seconds = 60 } = {}) {
    const registered = await this.transport(`${this.url}/v1/reference`, {
      method: 'PUT', headers: this.headers(), body: JSON.stringify({ text: reference }),
      signal: AbortSignal.timeout(10000),
    }).catch(() => null);
    if (!registered?.ok) return { status: 'unregistered' };
    this.reference = reference;
    const began = Date.now();
    try {
      const response = await this.transport(`${this.url}/v1/prepare`, {
        method: 'POST', headers: this.headers(), body: '{}', signal: AbortSignal.timeout(seconds * 1000),
      });
      const result = response.ok ? await response.json() : null;
      return { status: result?.status ?? 'failed', reference_chars: reference.length,
        seconds: result?.seconds ?? (Date.now() - began) / 1000 };
    } catch {
      return { status: 'failed', reference_chars: reference.length, seconds: (Date.now() - began) / 1000 };
    }
  }

  async sendRequest(turns, systemMessage, responseFormat = 'text') {
    const id = randomUUID();
    const controller = new AbortController();
    this.pending.set(id, controller);
    // CIEL already holds the registered fixed prefix; send only what changes per turn.
    const text = this.reference && systemMessage.startsWith(this.reference + '\n')
      ? systemMessage.slice(this.reference.length + 1) : systemMessage;
    // A CIEL session serves one request at a time. Mindcraft can summarize memory while the
    // next turn is prompted, so queue instead of letting the core answer 409 session_busy.
    const previous = this.queue;
    let release;
    const mine = new Promise(resolve => { release = resolve; });
    this.queue = mine;
    try {
      if (previous) await previous;
      if (controller.signal.aborted || !this.pending.has(id)) throw new Error('CIEL request cancelled');
      const messages = [
        { role: 'user', content: JSON.stringify({ type: 'execution_context', text }) },
        ...turns.map(turn => ({ role: turn.role === 'assistant' ? 'assistant' : 'user',
          content: turn.role === 'system' ? JSON.stringify({ type: 'execution_observation', text: turn.content }) : turn.content })),
      ];
      const response = await this.transport(`${this.url}/v1/respond`, {
        method: 'POST', headers: this.headers(), body: JSON.stringify({ request_id: id, messages, response_format: responseFormat }),
        signal: AbortSignal.any([controller.signal, AbortSignal.timeout(125000)]),
      });
      if (!response.ok) throw new Error(`CIEL inference failed: ${response.status}`);
      const result = await response.json();
      if (!this.pending.has(id)) throw new Error('CIEL request cancelled');
      if (result.request_id !== id || typeof result.text !== 'string') throw new Error('Invalid CIEL response');
      return result.text;
    } finally {
      this.pending.delete(id); release();
      if (this.queue === mine) this.queue = null;
    }
  }

  headers() { return { Authorization: `Bearer ${this.token}`, 'Content-Type': 'application/json' }; }

  async cancel() {
    const ids = [...this.pending.keys()];
    for (const controller of this.pending.values()) controller.abort(new Error('CIEL request cancelled'));
    this.pending.clear();
    await Promise.all(ids.map(async id => {
      const response = await this.transport(`${this.url}/v1/requests/${id}`, {
        method: 'DELETE', headers: this.headers(), signal: AbortSignal.timeout(5000),
      });
      if (!response.ok && response.status !== 404) throw new Error('CIEL cancellation unconfirmed');
    }));
  }
}
