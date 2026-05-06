/* API Communication Layer — REST calls + SSE streaming */

class TravelAPI {
  constructor(baseUrl = '/api/v1') {
    this.baseUrl = baseUrl;
    this.currentThreadId = null;
    this.eventSource = null;
  }

  /* ---- Shared fetch wrapper ---- */

  async _fetch(path, options = {}) {
    const res = await fetch(`${this.baseUrl}${path}`, options);
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    return res;
  }

  async _post(path, body) {
    const res = await this._fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    return res.json();
  }

  /* ---- Plan Creation ---- */

  async createPlan(query, profile = {}, model = '') {
    const body = { query, profile };
    if (model) body.model = model;
    const data = await this._post('/plan', body);
    this.currentThreadId = data.thread_id;
    return data;
  }

  /* ---- SSE Streaming ---- */

  streamPlan(threadId, callbacks = {}) {
    this.cancelStream();
    this.currentThreadId = threadId;

    this.eventSource = new EventSource(`${this.baseUrl}/plan/${threadId}/stream`);

    this.eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);

        if (data.type === SSE_EVENT.DONE) {
          this.cancelStream();
          callbacks.onDone?.(data);
          return;
        }

        if (data.type === SSE_EVENT.ERROR) {
          callbacks.onError?.(data);
          return;
        }

        callbacks.onEvent?.(data.type, data);
      } catch (e) {
        console.warn('Failed to parse SSE event:', event.data);
        callbacks.onError?.({ message: '数据解析失败' });
      }
    };

    this.eventSource.onerror = () => {
      this.cancelStream();
      callbacks.onError?.({ message: '连接中断' });
    };

    return this.eventSource;
  }

  cancelStream() {
    if (this.eventSource) {
      this.eventSource.close();
      this.eventSource = null;
    }
  }

  /* ---- Resume (Human input) ---- */

  async resumePlan(threadId, response) {
    return this._post(`/plan/${threadId}/resume`, { response });
  }

  /* ---- Status ---- */

  async getStatus(threadId) {
    const res = await this._fetch(`/plan/${threadId}/status`);
    return res.json();
  }

  /* ---- Models ---- */

  async getModels() {
    try {
      const res = await fetch(`${this.baseUrl}/models`);
      if (!res.ok) return { models: [], default: '' };
      return res.json();
    } catch {
      return { models: [], default: '' };
    }
  }

  /* ---- Cancel ---- */

  async cancelPlan(threadId) {
    await fetch(`${this.baseUrl}/plan/${threadId}`, { method: 'DELETE' });
    this.cancelStream();
  }

  /* ---- Export PDF ---- */

  exportPdfUrl(threadId) {
    return `${this.baseUrl}/plan/${threadId}/export/pdf`;
  }

  /* ---- Health ---- */

  async healthCheck() {
    try {
      const res = await fetch('/health');
      return res.ok;
    } catch {
      return false;
    }
  }
}

const api = new TravelAPI();
