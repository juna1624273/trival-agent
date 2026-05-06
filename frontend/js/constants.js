/* Shared constants for the travel planning frontend */

const AGENT_TYPES = Object.freeze({
  TRANSPORT: 'transport',
  MAPS: 'maps',
  WEATHER: 'weather',
  HOTEL: 'hotel',
  SEARCH: 'search',
  FILE: 'file',
});

const AGENT_LABELS = Object.freeze({
  transport: '交通',
  maps: '地图',
  weather: '天气',
  hotel: '酒店',
  search: '搜索',
  file: '文件',
});

const AGENT_ICONS = Object.freeze({
  transport: '✈️',
  maps: '🗺️',
  weather: '🌤️',
  hotel: '🏨',
  search: '🔍',
  file: '📄',
});

const TRANSPORT_ICONS = Object.freeze({
  flight: '✈️',
  train: '🚄',
  bus: '🚌',
  default: '🚌',
});

const STATUS = Object.freeze({
  PENDING: 'pending',
  RUNNING: 'running',
  COMPLETED: 'completed',
  FAILED: 'failed',
});

const STATUS_LABELS = Object.freeze({
  pending: '待执行',
  running: '执行中',
  completed: '已完成',
  failed: '失败',
});

const SSE_EVENT = Object.freeze({
  NODE_UPDATE: 'node_update',
  REACT_STEP: 'react_step',
  HUMAN_INPUT_REQUIRED: 'human_input_required',
  REPLAN: 'replan',
  FINALIZE: 'finalize',
  PHASE_CHANGE: 'phase_change',
  DONE: 'done',
  ERROR: 'error',
});

const PHASE = Object.freeze({
  PLAN: 'plan',
  EXECUTE: 'execute',
  REPLAN: 'replan',
  HUMAN_INPUT: 'human_input',
  FINALIZE: 'finalize',
  DONE: 'done',
});

const UI_STATE = Object.freeze({
  READY: 'ready',
  RUNNING: 'running',
  STREAMING: 'streaming',
  ERROR: 'error',
});

const UI_STATE_CONFIG = Object.freeze({
  ready: ['就绪', ''],
  running: ['执行中', 'running'],
  streaming: ['实时传输', 'streaming'],
  error: ['错误', 'error'],
});

const ITINERARY_DONE_MSG = '✅ 旅行攻略已生成！请切换到「旅行攻略」标签查看完整方案。';

/* Pre-compiled regexes for message formatting */
const FORMAT_RE = {
  bold: /\*\*(.*?)\*\*/g,
  italic: /\*(.*?)\*/g,
  codeBlock: /```(\w*)\n?([\s\S]*?)```/g,
  codeInline: /`([^`]+)`/g,
  entities: /[&<>]/g,
  newline: /\n/g,
};
