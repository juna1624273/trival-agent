/* Plan & Itinerary Visualization */

class PlanView {
  static STATUS_LABELS = STATUS_LABELS;

  static ITINERARY_SECTIONS = [
    { key: 'overview', icon: '📌', title: '行程概览', render: '_renderOverview' },
    { key: 'transport', icon: '✈️', title: '交通方案', render: '_renderTransport', isArray: true },
    { key: 'weather', icon: '🌤', title: '天气情况', render: '_renderWeather', isArray: true },
    { key: 'hotels', icon: '🏨', title: '住宿推荐', render: '_renderHotels', isArray: true },
    { key: 'daily_schedule', icon: '📅', title: '每日行程', render: '_renderDailySchedule', isArray: true },
    { key: 'attractions', icon: '🏯', title: '景点推荐', render: '_renderList', isArray: true },
    { key: 'restaurants', icon: '🍜', title: '美食推荐', render: '_renderList', isArray: true },
    { key: 'tips', icon: '💡', title: '出行贴士', render: '_renderTips', isArray: true },
    { key: 'budget_estimate', icon: '💰', title: '预算预估', render: '_renderBudget' },
  ];

  constructor() {
    this.container = document.getElementById('planContainer');
    this.itineraryContainer = document.getElementById('itineraryContainer');
    this.currentPlan = null;
    this.currentItinerary = null;
    this._stepDataCache = {};
  }

  /* ---- Render Plan Steps ---- */

  renderPlan(travelPlan, currentStepIndex = 0) {
    this._stepDataCache = {};

    if (!travelPlan || !travelPlan.steps) {
      this._showEmpty(this.container, '📋', '暂无执行计划');
      return;
    }

    this.currentPlan = travelPlan;
    const steps = travelPlan.steps;

    let html = '';

    const progress = steps.length > 0 ? Math.round((currentStepIndex / steps.length) * 100) : 0;
    html += `
      <div style="padding:16px 24px;">
        <div style="display:flex;justify-content:space-between;margin-bottom:6px;font-size:0.85rem;">
          <span>执行进度</span>
          <span>${currentStepIndex}/${steps.length} 步骤</span>
        </div>
        <div class="progress-bar">
          <div class="progress-bar-fill" style="width:${progress}%"></div>
        </div>
      </div>
    `;

    html += '<div style="padding:0 24px 24px;">';
    steps.forEach((step, i) => {
      let status = STATUS.PENDING;
      if (i < currentStepIndex) status = STATUS.COMPLETED;
      else if (i === currentStepIndex) status = STATUS.RUNNING;

      html += `
        <div class="plan-card" data-step-id="${step.step_id}" data-step-index="${i}">
          <div class="plan-card-header">
            <div class="step-number ${status}">${i + 1}</div>
            <div class="step-info">
              <div class="step-description">${step.description}</div>
              <span class="step-agent agent-${step.agent_type}">${AGENT_LABELS[step.agent_type] || step.agent_type}</span>
            </div>
            <div class="step-status ${status}">${PlanView.STATUS_LABELS[status]}</div>
          </div>
        </div>
      `;
    });
    html += '</div>';

    this.container.innerHTML = html;

    this.container.querySelectorAll('.plan-card').forEach(card => {
      card.addEventListener('click', () => {
        this._showStepDetail(parseInt(card.dataset.stepId));
      });
    });
  }

  updateStepStatus(stepId, status) {
    const card = this.container.querySelector(`[data-step-id="${stepId}"]`);
    if (!card) return;

    const numEl = card.querySelector('.step-number');
    if (numEl.classList.contains(status)) return;

    const statusEl = card.querySelector('.step-status');
    numEl.className = `step-number ${status}`;
    statusEl.className = `step-status ${status}`;
    statusEl.textContent = PlanView.STATUS_LABELS[status] || status;
  }

  /* ---- Step Detail (in panel) ---- */

  _showStepDetail(stepId) {
    if (!this.currentPlan) return;
    const step = this.currentPlan.steps.find(s => s.step_id === stepId);
    if (!step) return;

    const extraData = this._stepDataCache[stepId] || {};
    const contentHtml = `
      <div class="step-detail">
        <h4>步骤 #${stepId}: ${step.description}</h4>
        <div class="detail-section">
          <div class="detail-label">负责Agent</div>
          <div class="detail-value"><span class="step-agent agent-${step.agent_type}">${AGENT_LABELS[step.agent_type] || step.agent_type}</span></div>
        </div>
        <div class="detail-section">
          <div class="detail-label">输入参数</div>
          <div class="detail-value"><code>${JSON.stringify(step.input_params, null, 2)}</code></div>
        </div>
        <div class="detail-section">
          <div class="detail-label">预期输出</div>
          <div class="detail-value">${step.expected_output || '无'}</div>
        </div>
        ${extraData.observation ? `
        <div class="detail-section">
          <div class="detail-label">执行结果</div>
          <div class="detail-value">${extraData.observation}</div>
        </div>` : ''}
        ${extraData.reactTrace ? `
        <div class="detail-section">
          <div class="detail-label">ReAct 追踪</div>
          ${this._renderTraceDetails(extraData.reactTrace)}
        </div>` : ''}
      </div>`;

    ui.openPanel(`步骤 #${stepId} 详情`, contentHtml);
  }

  _renderTraceDetails(traces) {
    return traces.map(t => `
      <div class="react-trace">
        <div class="trace-phase think">💭 ${t.thought || ''}</div>
        <div class="trace-phase act">🔧 ${t.action || ''}</div>
        <div class="trace-phase observe">👁 ${t.observation || ''}</div>
      </div>
    `).join('');
  }

  cacheStepData(stepId, data) {
    if (!this._stepDataCache[stepId]) {
      this._stepDataCache[stepId] = {};
    }
    Object.assign(this._stepDataCache[stepId], data);
  }

  /* ---- Normalize LLM output to expected structure ---- */

  _normalizeItinerary(raw) {
    const n = {};

    // overview: try 'itinerary', 'overview', 'trip_overview', or use raw itself
    const overview = raw.itinerary || raw.overview || raw.trip_overview || {};
    n.overview = {
      destination: overview.destination || overview.title || raw.destination || '',
      duration: overview.duration || overview.date_range || overview.days || '',
      travelers: overview.travelers || '',
      total_budget: overview.total_budget_estimate || overview.total_budget || overview.budget || '',
    };

    // transport: flatten nested structure to flat array
    n.transport = [];
    const transport = raw.transport || raw.transportation || {};
    if (Array.isArray(transport)) {
      n.transport = transport;
    } else {
      for (const dir of ['to_hangzhou', 'from_hangzhou', 'outbound', 'return', 'to', 'from']) {
        const dirData = transport[dir];
        if (!dirData) continue;
        const options = dirData.options || dirData.recommended_trains || dirData.recommended_flights || [];
        if (Array.isArray(options)) {
          for (const opt of options) {
            const details = opt.details || [opt];
            for (const d of (Array.isArray(details) ? details : [details])) {
              n.transport.push({
                type: opt.type || d.type || d.train_number ? 'train' : 'flight',
                from: d.departure || d.from || '',
                to: d.arrival || d.to || '',
                departure_time: d.departure || d.departure_time || '',
                duration: d.duration || '',
                company: d.airline || d.train_number || d.company || '',
                price: d.price_range || d.price || '',
              });
            }
          }
        }
      }
    }

    // hotels: extract options array from accommodation/hotel object
    const accom = raw.accommodation || raw.hotel || raw.hotels || {};
    n.hotels = Array.isArray(accom) ? accom : (accom.options || accom.recommendations || []);
    if (!Array.isArray(n.hotels)) n.hotels = [];
    n.hotels = n.hotels.map(h => ({
      name: h.name || '',
      stars: h.stars || h.rating || 0,
      location: h.location || h.address || h.area || '',
      distance: h.distance || '',
      facilities: h.facilities || h.features || '',
      price: h.price_range || h.price || h.price_per_night || '',
    }));

    // weather: extract forecasts array
    const weather = raw.weather || {};
    n.weather = Array.isArray(weather) ? weather : (weather.forecasts || weather.forecast || []);
    if (typeof n.weather === 'string') n.weather = [];
    if (!Array.isArray(n.weather)) n.weather = [];
    n.weather = n.weather.map(w => ({
      date: w.date || '',
      condition: w.condition || w.weather || '',
      temp: w.temperature || w.temp || '',
      humidity: w.humidity || '',
      wind: w.wind_speed || w.wind || '',
      icon: w.icon || '🌤',
    }));

    // daily_schedule: normalize day structure
    const days = raw.daily_itinerary || raw.daily_schedule || raw.itinerary_days || [];
    n.daily_schedule = Array.isArray(days) ? days.map(d => ({
      date: d.date || '',
      items: (d.schedule || d.items || d.activities || []).map(a => ({
        time: a.time || '',
        activity: a.activity || a.description || '',
        description: a.note || a.description || '',
      })),
    })) : [];

    // attractions: extract from nested structure
    const attr = raw.attractions || raw.sightseeing || {};
    n.attractions = Array.isArray(attr) ? attr : (attr.must_visit || attr.recommended || attr.list || []);
    if (!Array.isArray(n.attractions)) n.attractions = [];
    n.attractions = n.attractions.map(a => ({
      name: a.name || '',
      description: a.note || a.description || a.ticket_price || '',
      rating: a.rating || '',
      price: a.ticket_price || a.price || '',
    }));

    // restaurants: extract from food_recommendations
    const food = raw.food_recommendations || raw.food || raw.restaurants || {};
    n.restaurants = Array.isArray(food) ? food : (food.recommended_restaurants || food.list || []);
    if (!Array.isArray(n.restaurants)) n.restaurants = [];
    n.restaurants = n.restaurants.map(r => ({
      name: r.name || '',
      description: r.specialty || r.cuisine || r.description || '',
      rating: r.rating || '',
      price: r.price_range || r.price || r.budget || '',
    }));

    // tips: flatten object-of-arrays to flat array
    const tips = raw.tips || raw.travel_tips || {};
    if (Array.isArray(tips)) {
      n.tips = tips;
    } else {
      n.tips = [];
      for (const [, val] of Object.entries(tips)) {
        if (Array.isArray(val)) {
          n.tips.push(...val);
        } else if (typeof val === 'string') {
          n.tips.push(val);
        }
      }
    }

    // budget_estimate: normalize
    const budget = raw.budget_breakdown || raw.budget_estimate || raw.budget || {};
    if (typeof budget === 'object' && !Array.isArray(budget)) {
      const items = budget.items || [];
      const estimate = { total: parseInt(budget.total) || budget.total || 0 };
      if (Array.isArray(items)) {
        for (const item of items) {
          estimate[item.category || item.name || ''] = parseInt(item.cost) || item.cost || 0;
        }
      } else {
        Object.assign(estimate, budget);
      }
      n.budget_estimate = estimate;
    } else {
      n.budget_estimate = { total: budget };
    }

    return n;
  }

  /* ---- Render Itinerary ---- */

  renderItinerary(itinerary) {
    if (!itinerary || Object.keys(itinerary).length === 0) {
      this._showEmpty(this.itineraryContainer, '📝', '暂无旅行攻略');
      return;
    }

    const normalized = this._normalizeItinerary(itinerary);
    this.currentItinerary = itinerary;
    document.getElementById('exportPdfBtn').disabled = false;
    document.getElementById('exportExcelBtn').disabled = false;

    let html = '<div style="padding:24px;overflow-y:auto;">';

    for (const section of PlanView.ITINERARY_SECTIONS) {
      const data = normalized[section.key];
      if (!data || (section.isArray && !Array.isArray(data)) || (section.isArray && data.length === 0)) continue;
      html += this._renderSection(section.icon, section.title, this[section.render](data));
    }

    html += '</div>';
    this.itineraryContainer.innerHTML = html;
  }

  /* ---- Section Helpers ---- */

  _renderSection(icon, title, content) {
    return `
      <div class="itinerary-card">
        <div class="itinerary-section">
          <h4><span class="section-icon">${icon}</span>${title}</h4>
          ${content}
        </div>
      </div>`;
  }

  _renderOverview(data) {
    const items = [];
    if (data.destination) items.push(`<strong>目的地：</strong>${data.destination}`);
    if (data.duration) items.push(`<strong>天数：</strong>${data.duration}`);
    if (data.travelers) items.push(`<strong>人数：</strong>${data.travelers}`);
    if (data.total_budget) items.push(`<strong>总预算：</strong>¥${data.total_budget}`);
    return items.map(i => `<div style="margin-bottom:4px;">${i}</div>`).join('');
  }

  _renderTransport(items) {
    return items.map(t => `
      <div class="info-card">
        <div class="card-icon">${TRANSPORT_ICONS[t.type] || TRANSPORT_ICONS.default}</div>
        <div class="card-details">
          <div class="card-title">${t.from || ''} → ${t.to || ''}</div>
          <div class="card-subtitle">${t.departure_time || ''} · ${t.duration || ''} · ${t.company || ''}</div>
        </div>
        <div class="card-price">${t.price ? '¥' + t.price : ''}</div>
      </div>
    `).join('');
  }

  _renderWeather(items) {
    return items.map(w => `
      <div class="info-card">
        <div class="card-icon">${w.icon || '🌤'}</div>
        <div class="card-details">
          <div class="card-title">${w.date || ''} · ${w.condition || ''}</div>
          <div class="card-subtitle">🌡 ${w.temp || ''} · 💧 ${w.humidity || ''} · 🌬 ${w.wind || ''}</div>
        </div>
      </div>
    `).join('');
  }

  _renderHotels(items) {
    return items.map(h => `
      <div class="info-card">
        <div class="card-icon">🏨</div>
        <div class="card-details">
          <div class="card-title">${h.name || ''} ${'⭐'.repeat(h.stars || 0)}</div>
          <div class="card-subtitle">📍 ${h.location || ''} · ${h.distance || ''} · ${h.facilities || ''}</div>
        </div>
        <div class="card-price">¥${h.price || '--'}/晚</div>
      </div>
    `).join('');
  }

  _renderDailySchedule(days) {
    return days.map((day, i) => `
      <div class="day-card">
        <div class="day-header">📅 第${i + 1}天 ${day.date || ''}</div>
        <div class="timeline">
          ${(day.items || day.activities || []).map(item => `
            <div class="timeline-item">
              <strong>${item.time || ''}</strong> ${item.activity || item.description || item}
            </div>
          `).join('')}
        </div>
      </div>
    `).join('');
  }

  _renderList(items) {
    return items.map(item => `
      <div class="info-card">
        <div class="card-icon">📍</div>
        <div class="card-details">
          <div class="card-title">${item.name || item}</div>
          ${item.description ? `<div class="card-subtitle">${item.description}</div>` : ''}
          ${item.rating ? `<div class="card-subtitle">⭐ ${item.rating}</div>` : ''}
        </div>
        ${item.price ? `<div class="card-price">¥${item.price}</div>` : ''}
      </div>
    `).join('');
  }

  _renderTips(items) {
    return `<ul>${items.map(t => `<li>${t}</li>`).join('')}</ul>`;
  }

  _renderBudget(data) {
    const total = data.total || 0;
    const items = [];
    for (const [key, val] of Object.entries(data)) {
      if (key !== 'total') {
        const pct = total > 0 ? Math.round((val / total) * 100) : 0;
        items.push(`
          <div style="display:flex;justify-content:space-between;margin-bottom:4px;font-size:0.85rem;">
            <span>${key}</span>
            <span>¥${val} (${pct}%)</span>
          </div>
          <div class="budget-bar"><div class="budget-bar-fill" style="width:${pct}%"></div></div>
        `);
      }
    }
    return items.join('');
  }

  _showEmpty(container, icon, text) {
    container.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">${icon}</div>
        <p>${text}</p>
        <span>先在对话中输入旅行需求，系统会自动生成</span>
      </div>`;
  }
}

const planView = new PlanView();
