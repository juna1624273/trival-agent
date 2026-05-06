/* UI Utilities — Message rendering, tabs, toasts, modals */

class UI {
  constructor() {
    this.messagesContainer = document.getElementById('messagesContainer');
    this.messageInput = document.getElementById('messageInput');
    this.sendBtn = document.getElementById('sendBtn');
    this.thinkingEl = null;
  }

  /* ---- Messages ---- */

  addMessage(role, content, extra = {}) {
    this.removeThinking();

    const msg = document.createElement('div');
    msg.className = `message ${role}`;

    const avatar = role === 'user' ? '👤' : '🤖';

    let bubbleHtml = this._formatContent(content);

    if (extra.planSteps) {
      bubbleHtml += this._renderMiniPlan(extra.planSteps);
    }

    if (extra.reactTraces) {
      bubbleHtml += this._renderReActTraces(extra.reactTraces);
    }

    msg.innerHTML = `
      <div class="message-avatar">${avatar}</div>
      <div class="message-bubble">${bubbleHtml}</div>
    `;

    this.messagesContainer.appendChild(msg);
    this._scrollToBottom();

    return msg;
  }

  addHumanQuestion(question, options = []) {
    this.removeThinking();
    this._removeExistingHumanQuestions();

    const msg = document.createElement('div');
    msg.className = 'message assistant human-question-msg';

    let optionsHtml = '';
    if (options.length > 0) {
      optionsHtml = `<div class="quick-reply-btns">${options.map(o =>
        `<button class="quick-reply-btn" data-reply="${o}">${o}</button>`
      ).join('')}</div>`;
    }

    msg.innerHTML = `
      <div class="message-avatar">🤖</div>
      <div class="message-bubble">
        <div class="human-question">
          <div class="question-text">🤔 ${question}</div>
          <div class="question-hint">请回复以上问题，系统将继续为您规划</div>
          ${optionsHtml}
        </div>
      </div>
    `;

    this.messagesContainer.appendChild(msg);
    this._scrollToBottom();

    msg.querySelectorAll('.quick-reply-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        document.dispatchEvent(new CustomEvent('quickReply', { detail: btn.dataset.reply }));
      });
    });

    return msg;
  }

  _removeExistingHumanQuestions() {
    this.messagesContainer.querySelectorAll('.human-question-msg').forEach(el => el.remove());
  }

  addSystemMessage(text) {
    const el = document.createElement('div');
    el.style.cssText = 'text-align:center;font-size:0.8rem;color:var(--text-muted);padding:8px;';
    el.textContent = text;
    this.messagesContainer.appendChild(el);
    this._scrollToBottom();
  }

  showThinking(text = '正在分析...') {
    this.removeThinking();
    const el = document.createElement('div');
    el.className = 'thinking-indicator';
    el.id = 'thinkingIndicator';
    el.innerHTML = `
      <div class="typing-dots"><span></span><span></span><span></span></div>
      <span>${text}</span>
    `;
    this.messagesContainer.appendChild(el);
    this._scrollToBottom();
    this.thinkingEl = el;
  }

  updateThinking(text) {
    if (!this.thinkingEl) return;
    const span = this.thinkingEl.querySelector('span');
    if (span.textContent === text) return;
    span.textContent = text;
  }

  removeThinking() {
    if (this.thinkingEl) {
      this.thinkingEl.remove();
      this.thinkingEl = null;
    }
  }

  /* ---- Tab Switching ---- */

  switchTab(tabName) {
    document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));

    const tabEl = document.getElementById(`tab-${tabName}`);
    if (tabEl) tabEl.classList.add('active');

    const btnEl = document.querySelector(`[data-tab="${tabName}"]`);
    if (btnEl) btnEl.classList.add('active');
  }

  /* ---- Toast ---- */

  showToast(message, type = 'success', duration = 3000) {
    const container = document.getElementById('toastContainer');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    container.appendChild(toast);

    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateX(80px)';
      toast.style.transition = 'all 0.3s';
      setTimeout(() => toast.remove(), 300);
    }, duration);
  }

  /* ---- Modal ---- */

  showFeedbackModal(onSubmit) {
    const modal = document.getElementById('feedbackModal');
    const textarea = document.getElementById('feedbackText');
    modal.classList.add('open');
    textarea.value = '';
    textarea.focus();

    const submit = () => {
      const text = textarea.value.trim();
      if (text) {
        modal.classList.remove('open');
        try {
          onSubmit(text);
        } catch (e) {
          console.error('Feedback submit error:', e);
        }
      }
    };

    document.getElementById('submitFeedback').onclick = submit;
    document.getElementById('closeFeedbackModal').onclick = () => modal.classList.remove('open');
    document.getElementById('cancelFeedback').onclick = () => modal.classList.remove('open');

    modal.onclick = (e) => {
      if (e.target === modal) modal.classList.remove('open');
    };

    textarea.onkeydown = (e) => {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit(); }
    };
  }

  /* ---- Detail Panel ---- */

  openPanel(title, contentHtml) {
    const panel = document.getElementById('detailPanel');
    document.getElementById('panelTitle').textContent = title;
    document.getElementById('panelContent').innerHTML = contentHtml;
    panel.classList.add('open');
  }

  closePanel() {
    document.getElementById('detailPanel').classList.remove('open');
  }

  /* ---- Status ---- */

  setStatus(state) {
    const indicator = document.getElementById('statusIndicator');
    const text = indicator.querySelector('.status-text');
    indicator.className = 'status-indicator';

    const [label, cls] = UI_STATE_CONFIG[state] || UI_STATE_CONFIG.ready;
    text.textContent = label;
    if (cls) indicator.classList.add(cls);
  }

  /* ---- Helpers ---- */

  _formatContent(text) {
    if (!text) return '';
    return text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(FORMAT_RE.bold, '<strong>$1</strong>')
      .replace(FORMAT_RE.italic, '<em>$1</em>')
      .replace(FORMAT_RE.codeBlock, '<pre><code>$2</code></pre>')
      .replace(FORMAT_RE.codeInline, '<code>$1</code>')
      .replace(FORMAT_RE.newline, '<br>');
  }

  _renderMiniPlan(steps) {
    if (!steps || steps.length === 0) return '';
    return `
      <div style="margin-top:12px;font-size:0.82rem;">
        <strong>📋 执行计划：</strong>
        ${steps.map(s => `
          <div style="display:flex;align-items:center;gap:8px;padding:4px 0;">
            <span class="agent-${s.agent_type}" style="font-size:0.7rem;padding:1px 8px;border-radius:10px;">
              ${AGENT_LABELS[s.agent_type] || s.agent_type}
            </span>
            <span>${s.description}</span>
          </div>
        `).join('')}
      </div>`;
  }

  _renderReActTraces(traces) {
    if (!traces || traces.length === 0) return '';
    return `
      <div style="margin-top:12px;">
        ${traces.map(t => `
          <div class="react-trace" style="margin-top:6px;">
            <div class="trace-phase think">💭 思考: ${this._formatContent(t.thought || '')}</div>
            <div class="trace-phase act">🔧 行动: <code>${t.action || ''}</code></div>
            <div class="trace-phase observe">👁 观察: ${t.observation ? this._truncate(t.observation, 200) : ''}</div>
            ${t.complete ? '✅ 完成' : '🔄 继续'}
          </div>
        `).join('')}
      </div>`;
  }

  _truncate(text, max) {
    if (!text || text.length <= max) return text;
    return text.substring(0, max) + '...';
  }

  _scrollToBottom() {
    this.messagesContainer.scrollTop = this.messagesContainer.scrollHeight;
  }
}

const ui = new UI();
