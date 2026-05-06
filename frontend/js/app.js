/* Main Application Controller */

class App {
  constructor() {
    this.isProcessing = false;
    this.userProfile = this._loadProfile();
    this.selectedModel = this._loadModel();
    this.messageInput = document.getElementById('messageInput');
    this.sendBtn = document.getElementById('sendBtn');
    this.init();
  }

  init() {
    this._bindEvents();
    this._createParticles();
    this._autoResizeTextarea();
    this._loadModels();
    ui.setStatus(UI_STATE.READY);

    api.healthCheck().then(ok => {
      if (!ok) ui.showToast('后端服务未连接，请检查', 'warning', 5000);
    }).catch(() => {
      ui.showToast('后端服务未连接，请检查', 'warning', 5000);
    });
  }

  /* ---- Event Binding ---- */

  _bindEvents() {
    this.sendBtn.addEventListener('click', () => this._sendMessage());
    this.messageInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        this._sendMessage();
      }
    });

    document.querySelectorAll('.prompt-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        this.messageInput.value = btn.dataset.prompt;
        this._sendMessage();
      });
    });

    document.addEventListener('quickReply', (e) => {
      this._handleHumanResponse(e.detail);
    });

    document.querySelectorAll('.nav-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        ui.switchTab(btn.dataset.tab);
      });
    });

    document.getElementById('closePanel').addEventListener('click', () => ui.closePanel());

    document.getElementById('exportExcelBtn')?.addEventListener('click', () => {
      if (planView.currentItinerary) {
        this._downloadBlob(
          new Blob([JSON.stringify(planView.currentItinerary, null, 2)], { type: 'application/json' }),
          `travel_itinerary_${Date.now()}.json`,
          '已导出 JSON 文件'
        );
      }
    });

    document.getElementById('exportPdfBtn')?.addEventListener('click', async () => {
      if (!api.currentThreadId) {
        ui.showToast('没有可导出的攻略，请先生成旅行计划', 'warning');
        return;
      }
      try {
        const url = api.exportPdfUrl(api.currentThreadId);
        const res = await fetch(url);
        if (!res.ok) {
          const err = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
          throw new Error(err.detail || '导出失败');
        }
        const blob = await res.blob();
        // Extract filename from server Content-Disposition header
        let filename = `旅行攻略_${Date.now()}.pdf`;
        const disposition = res.headers.get('Content-Disposition');
        if (disposition) {
          const starMatch = disposition.match(/filename\*=UTF-8''(.+)/);
          if (starMatch) {
            filename = decodeURIComponent(starMatch[1]);
          } else {
            const plainMatch = disposition.match(/filename="?([^";\n]+)"?/);
            if (plainMatch) filename = plainMatch[1];
          }
        }
        this._downloadBlob(blob, filename, 'PDF 下载成功');
      } catch (err) {
        console.error('PDF export failed:', err);
        ui.showToast(`PDF 导出失败：${err.message}`, 'error');
      }
    });

    document.getElementById('saveSettingsBtn')?.addEventListener('click', () => this._saveSettings());

    window.addEventListener('beforeunload', () => {
      api.cancelStream();
    });
  }

  /* ---- Message Handling ---- */

  async _sendMessage() {
    if (this.isProcessing) return;

    const query = this.messageInput.value.trim();
    if (!query) return;

    this.messageInput.value = '';
    this.messageInput.style.height = 'auto';

    ui.addMessage('user', query);
    ui.showThinking('正在分析需求，生成执行计划...');
    ui.setStatus(UI_STATE.RUNNING);
    this.isProcessing = true;
    this.sendBtn.disabled = true;

    try {
      const result = await api.createPlan(query, this.userProfile, this.selectedModel);

      if (result.needs_human && result.human_question) {
        this._displayHumanQuestion(result);
      }

      if (result.travel_plan) {
        planView.renderPlan(result.travel_plan, result.current_step_index || 0);
        ui.addMessage('assistant', this._summarizePlan(result.travel_plan), {
          planSteps: result.travel_plan.steps,
        });
      }

      if (result.final_itinerary) {
        planView.renderItinerary(result.final_itinerary);
        ui.addMessage('assistant', ITINERARY_DONE_MSG);
      }

      if (result.phase !== PHASE.DONE) {
        this._startStreaming();
      } else {
        this._resetUIState();
        ui.addSystemMessage('— 规划完成 —');
      }

    } catch (err) {
      console.error('Plan creation failed:', err);
      ui.removeThinking();
      ui.addMessage('assistant', `❌ 规划失败：${err.message}。请检查后端服务是否正常运行。`);
      ui.setStatus(UI_STATE.ERROR);
      ui.showToast('规划失败，请重试', 'error');
      this._resetUIState();
    }
  }

  _startStreaming() {
    if (!api.currentThreadId) return;

    ui.updateThinking('实时监听执行进度...');
    ui.setStatus(UI_STATE.STREAMING);

    api.streamPlan(api.currentThreadId, {
      onEvent: (type, data) => {
        switch (type) {
          case SSE_EVENT.NODE_UPDATE:
            this._handleNodeUpdate(data);
            break;
          case SSE_EVENT.REACT_STEP:
            this._handleReActStep(data);
            break;
          case SSE_EVENT.HUMAN_INPUT_REQUIRED:
            this._handleHumanInputRequired(data);
            break;
          case SSE_EVENT.REPLAN:
            this._handleReplan(data);
            break;
          case SSE_EVENT.FINALIZE:
            this._handleFinalize(data);
            break;
          case SSE_EVENT.PHASE_CHANGE:
            break;
        }
      },
      onDone: () => {
        ui.removeThinking();
        ui.setStatus(UI_STATE.READY);
        this._resetUIState();
        ui.addSystemMessage('— 规划完成 —');
      },
      onError: (data) => {
        ui.removeThinking();
        ui.setStatus(UI_STATE.ERROR);
        this._resetUIState();
        ui.showToast(data.message || '连接中断', 'error');
      },
    });
  }

  _handleNodeUpdate(data) {
    switch (data.node) {
      case PHASE.PLAN:
        if (data.phase === PHASE.EXECUTE) ui.updateThinking('计划生成完成，开始执行...');
        break;
      case PHASE.EXECUTE:
        ui.updateThinking('Agent 正在执行任务...');
        break;
      case PHASE.REPLAN:
        ui.updateThinking('正在评估结果...');
        break;
    }

    if (data.travel_plan) {
      planView.renderPlan(data.travel_plan, data.current_step_index || 0);
    }
  }

  _handleReActStep(data) {
    const traces = data.data || [];
    if (traces.length === 0) return;

    const last = traces[traces.length - 1];
    ui.updateThinking(`💭 ${last.thought || '执行中...'}`);

    if (last.step_id !== undefined) {
      planView.cacheStepData(last.step_id, {
        reactTrace: traces,
        observation: last.observation,
      });
      planView.updateStepStatus(last.step_id, last.complete ? STATUS.COMPLETED : STATUS.RUNNING);
    }
  }

  _handleHumanInputRequired(data) {
    ui.removeThinking();
    ui.setStatus(UI_STATE.READY);
    this.sendBtn.disabled = false;

    const questionData = data.data || data;
    ui.addHumanQuestion(questionData.question || '请提供更多信息', questionData.options || []);
    ui.showToast('需要您的补充信息', 'warning', 5000);
  }

  async _handleHumanResponse(response) {
    if (!api.currentThreadId) return;

    ui.showThinking('正在根据您的回复调整计划...');
    ui.setStatus(UI_STATE.RUNNING);

    try {
      const result = await api.resumePlan(api.currentThreadId, response);

      if (result.travel_plan) {
        planView.renderPlan(result.travel_plan, result.current_step_index || 0);
      }

      if (result.final_itinerary) {
        planView.renderItinerary(result.final_itinerary);
      }

      if (result.phase !== PHASE.DONE) {
        this._startStreaming();
      } else {
        ui.removeThinking();
        ui.setStatus(UI_STATE.READY);
        ui.addMessage('assistant', '✅ 规划已更新完成！');
      }
    } catch (err) {
      ui.removeThinking();
      ui.setStatus(UI_STATE.ERROR);
      ui.showToast('回复处理失败', 'error');
    }
  }

  _handleReplan(data) {
    const d = data.data || data;
    if (d.phase === PHASE.FINALIZE) {
      ui.updateThinking('即将生成最终攻略...');
    }
  }

  _handleFinalize(data) {
    ui.removeThinking();
    const itinerary = (data.data || data).itinerary || data.final_itinerary;
    if (itinerary) {
      try {
        planView.renderItinerary(itinerary);
        ui.addMessage('assistant', ITINERARY_DONE_MSG);
        ui.showToast('攻略生成完成', 'success');
      } catch (err) {
        console.error('Failed to render itinerary:', err);
        ui.addMessage('assistant', '✅ 旅行攻略已生成！请切换到「旅行攻略」标签查看。');
      }
    }
  }

  _displayHumanQuestion(result) {
    const q = result.human_question;
    ui.removeThinking();
    ui.setStatus(UI_STATE.READY);
    this.sendBtn.disabled = false;
    ui.addHumanQuestion(q.question, q.options || []);
  }

  /* ---- Utilities ---- */

  _resetUIState() {
    this.isProcessing = false;
    this.sendBtn.disabled = false;
  }

  _downloadBlob(blob, filename, successMsg) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    ui.showToast(successMsg, 'success');
  }

  _summarizePlan(plan) {
    if (!plan || !plan.steps) return '已生成执行计划';
    const stepList = plan.steps.map(s =>
      `${s.step_id}. [${AGENT_LABELS[s.agent_type] || s.agent_type}] ${s.description}`
    ).join('\n');
    return `📋 **已为您生成 ${plan.steps.length} 步执行计划：**\n\n${stepList}\n\n系统正在按步骤执行，请稍候...`;
  }

  _autoResizeTextarea() {
    const ta = this.messageInput;
    let rafPending = null;
    ta.addEventListener('input', () => {
      if (rafPending) cancelAnimationFrame(rafPending);
      rafPending = requestAnimationFrame(() => {
        ta.style.height = 'auto';
        ta.style.height = Math.min(ta.scrollHeight, 120) + 'px';
      });
    });
  }

  _createParticles() {
    const container = document.getElementById('particles');
    if (!container) return;
    const colors = ['#6366f1', '#06b6d4', '#10b981', '#f59e0b'];

    for (let i = 0; i < 30; i++) {
      const particle = document.createElement('div');
      particle.className = 'particle';
      const size = Math.random() * 4 + 2;
      particle.style.cssText = `
        width: ${size}px; height: ${size}px;
        left: ${Math.random() * 100}%;
        top: ${Math.random() * 100}%;
        background: ${colors[Math.floor(Math.random() * colors.length)]};
        animation-delay: ${Math.random() * 10}s;
        animation-duration: ${6 + Math.random() * 8}s;
      `;
      container.appendChild(particle);
    }
  }

  _loadProfile() {
    try {
      const saved = localStorage.getItem('travel_profile');
      if (saved) return JSON.parse(saved);
    } catch {}
    return {};
  }

  _loadModel() {
    try {
      return localStorage.getItem('travel_model') || '';
    } catch {
      return '';
    }
  }

  _saveSettings() {
    this.userProfile = {
      home_city: document.getElementById('settingHomeCity')?.value || undefined,
      budget_level: document.getElementById('settingBudget')?.value || undefined,
      preferred_transport: Array.from(document.querySelectorAll('.transport-check:checked')).map(c => c.value),
      hotel_preferences: Array.from(document.querySelectorAll('.hotel-check:checked')).map(c => c.value),
    };
    this.selectedModel = document.getElementById('settingModel')?.value || '';
    try {
      localStorage.setItem('travel_profile', JSON.stringify(this.userProfile));
      localStorage.setItem('travel_model', this.selectedModel);
    } catch {}
    ui.showToast('设置已保存', 'success');
    ui.switchTab('chat');
  }

  async _loadModels() {
    const select = document.getElementById('settingModel');
    if (!select) return;

    let models = [];
    let defaultId = '';
    try {
      const data = await api.getModels();
      models = data.models || [];
      defaultId = data.default || '';
    } catch {
      models = [
        { id: 'deepseek-chat', label: 'DeepSeek V3' },
        { id: 'deepseek-reasoner', label: 'DeepSeek R1' },
        { id: 'qwen-plus', label: '通义千问 Plus' },
        { id: 'qwen-max', label: '通义千问 Max' },
        { id: 'qwen-turbo', label: '通义千问 Turbo' },
        { id: 'moonshot-v1-8k', label: 'Kimi 8K' },
        { id: 'moonshot-v1-32k', label: 'Kimi 32K' },
        { id: 'moonshot-v1-128k', label: 'Kimi 128K' },
        { id: 'gpt-4o', label: 'GPT-4o' },
        { id: 'gpt-4o-mini', label: 'GPT-4o Mini' },
      ];
    }

    if (!this.selectedModel && defaultId) {
      try { localStorage.setItem('travel_model', defaultId); } catch {}
    }

    select.innerHTML = '';
    if (models.length === 0 || !defaultId) {
      select.innerHTML = '<option value="">默认 (DeepSeek V3)</option>';
    }
    models.forEach(m => {
      const opt = document.createElement('option');
      opt.value = m.id;
      opt.textContent = m.label;
      if (m.id === defaultId) opt.textContent += ' (默认)';
      if (m.id === this.selectedModel) opt.selected = true;
      select.appendChild(opt);
    });
  }
}

document.addEventListener('DOMContentLoaded', () => {
  window.app = new App();
});
