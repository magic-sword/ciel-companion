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
  }

  async sendRequest(turns, systemMessage, responseFormat = 'text') {
    const id = randomUUID();
    const controller = new AbortController();
    this.pending.set(id, controller);
    try {
      const messages = [
        { role: 'user', content: JSON.stringify({ type: 'execution_context', text: systemMessage }) },
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
    } finally { this.pending.delete(id); }
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
