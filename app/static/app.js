const originalFetch = window.fetch;
window.fetch = async (...args) => {
  const response = await originalFetch(...args);
  if (response.status === 401) {
    const url = typeof args[0] === 'string' ? args[0] : (args[0]?.url || '');
    if (!url.includes('/api/auth/login') && !url.includes('/api/auth/me')) {
      window.location.href = '/login';
    }
  }
  return response;
};

const DEFAULT_REFRESH_MS = 5 * 60 * 1000;
const SETTINGS_LIMITS = {
  daily_swing_candles: { min: 60, max: 1500, type: 'int', label: 'Velas históricas — Swing actual' },
  backtest_candles: { min: 120, max: 5000, type: 'int', label: 'Velas diarias cerradas — Backtest' },
  lookback_days: { min: 1, max: 5000, type: 'int', label: 'Ventana estructural diaria' },
  pivot_left: { min: 1, max: 20, type: 'int', label: 'Pivot izquierda' },
  pivot_right: { min: 1, max: 20, type: 'int', label: 'Pivot derecha' },
  min_confirmations: { min: 1, max: 20, type: 'int', label: 'Confirmaciones mínimas' },
  cluster_tolerance_pct: { min: 0, max: 100, type: 'float', label: 'Tolerancia cluster (%)' },
  sma20_filter_pct: { min: 0, max: 100, type: 'float', label: 'Filtro SMA20 (%)' },
  operational_range_pct: { min: 0, max: 100, type: 'float', label: 'Distancia máxima a niveles (%)' },
  min_operational_range_pct: { min: 0, max: 100, type: 'float', label: 'Amplitud mínima del rango (%)' },
  pnl_chart_days: { min: 7, max: 90, type: 'int', label: 'Ventana gráfica PnL acumulado' },
  volume_baseline_period: { min: 5, max: 168, type: 'int', label: 'Ventana de referencia de volumen (h)' },
  volume_confirmation_threshold: { min: 0.50, max: 5.00, type: 'float', label: 'Umbral de volumen relativo (x)' },
};

const money = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  maximumFractionDigits: 0,
});

const moneyPrecise = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

let refreshTimer = null;
let refreshInFlight = false;
let historyRefreshInFlight = false;
let refreshIntervalMs = DEFAULT_REFRESH_MS;
let lastValidTimestampIso = null;
const AUTOMATION_STALE_THRESHOLD_MS = 10 * 60 * 1000;
const TELEGRAM_TEST_IDLE_TEXT = 'ENVIAR MENSAJE DE PRUEBA';
const TELEGRAM_TEST_BUSY_TEXT = 'Enviando...';
const SIGNAL_STATE_VISUALS = {
  NO_TRADE: {
    label: 'NO TRADE',
    interpretation: 'El precio esta fuera de una zona operable.',
    step: 1,
    chipClass: 'chip-neutral',
  },
  WATCH: {
    label: 'ESPERA',
    interpretation: 'Zona direccional detectada. Esperando confirmacion.',
    step: 2,
    chipClass: 'chip-watch',
  },
  HIGH: {
    label: 'CONFIRMADO',
    interpretation: 'Setup confirmado. Posible activacion inminente.',
    step: 3,
    chipClass: 'chip-high',
  },
  VERY_HIGH: {
    label: 'ACTIVO',
    interpretation: 'Trade operativo disponible.',
    step: 4,
    chipClass: 'chip-very-high',
  },
};

const SIGNAL_DIRECTION_VISUALS = {
  LONG: {
    label: 'Largo',
    arrow: '↑',
    className: 'signal-direction-long',
  },
  SHORT: {
    label: 'Corto',
    arrow: '↓',
    className: 'signal-direction-short',
  },
  NEUTRAL: {
    label: 'Neutral',
    arrow: '—',
    className: 'signal-direction-neutral',
  },
};

function byId(id) {
  return document.getElementById(id);
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function asMoney(value) {
  return value == null ? '—' : money.format(value);
}

function asMoneyPrecise(value) {
  if (value == null || Number.isNaN(Number(value))) {
    return '—';
  }
  return moneyPrecise.format(Number(value));
}

function asClusterMoney(value) {
  if (value == null || Number.isNaN(Number(value))) {
    return '—';
  }

  const amount = Number(value);
  const sign = amount < 0 ? '-' : '';
  const absolute = Math.abs(amount);
  const [integerPartRaw, decimalPartRaw] = absolute.toString().split('.');
  const groupedInteger = Number(integerPartRaw).toLocaleString('en-US');

  if (!decimalPartRaw) {
    return `${sign}$${groupedInteger}`;
  }

  return `${sign}$${groupedInteger}.${decimalPartRaw}`;
}

function asNumber(value, decimals = 2) {
  if (value == null || Number.isNaN(Number(value))) {
    return '—';
  }
  return Number(value).toFixed(decimals);
}

function asCompactUsd(value) {
  if (value == null || Number.isNaN(Number(value))) {
    return '—';
  }

  const amount = Number(value);
  if (amount >= 1_000_000_000) {
    return `$${(amount / 1_000_000_000).toFixed(2)}B`;
  }
  if (amount >= 1_000_000) {
    return `$${(amount / 1_000_000).toFixed(1)}M`;
  }
  if (amount >= 1_000) {
    return `$${Math.round(amount / 1_000)}K`;
  }
  return asMoney(amount);
}

function asCompactBtc(value) {
  if (value == null || Number.isNaN(Number(value))) {
    return '—';
  }

  const amount = Number(value);
  const decimals = amount >= 100 ? 0 : 3;
  return Number(amount).toFixed(decimals);
}

function formatTimeFromIso(isoTimestamp) {
  if (!isoTimestamp) {
    return '—';
  }

  const date = new Date(isoTimestamp);
  if (Number.isNaN(date.getTime())) {
    return '—';
  }

  return new Intl.DateTimeFormat('es-ES', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(date);
}

function formatDateTimeFromIso(isoTimestamp) {
  if (!isoTimestamp) {
    return '—';
  }

  const date = new Date(isoTimestamp);
  if (Number.isNaN(date.getTime())) {
    return '—';
  }

  return new Intl.DateTimeFormat('es-ES', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(date);
}

function formatHistoryDateTimeFromIso(isoTimestamp) {
  if (!isoTimestamp) {
    return '—';
  }

  const date = new Date(isoTimestamp);
  if (Number.isNaN(date.getTime())) {
    return '—';
  }

  const dayMonth = new Intl.DateTimeFormat('es-ES', {
    day: '2-digit',
    month: 'short',
  }).format(date).replace('.', '').toLowerCase();

  return `${dayMonth} · ${formatTimeFromIso(isoTimestamp)}`;
}

function formatDayMonth(isoTimestamp) {
  if (!isoTimestamp) {
    return '—';
  }

  const date = new Date(isoTimestamp);
  if (Number.isNaN(date.getTime())) {
    return '—';
  }

  const parts = new Intl.DateTimeFormat('es-ES', {
    day: '2-digit',
    month: 'short',
    timeZone: 'UTC',
  }).formatToParts(date);

  const day = parts.find((part) => part.type === 'day')?.value || '—';
  const monthRaw = parts.find((part) => part.type === 'month')?.value || '';
  const month = monthRaw.replace('.', '').toLowerCase();
  return `${day} ${month}`.trim();
}

function formatWindowDate(value) {
  if (!value) {
    return '—';
  }
  const normalized = value.length === 10 ? `${value}T00:00:00Z` : value;
  return formatDayMonth(normalized);
}

function mapStochStateLabel(state) {
  if (state === 'OVERBOUGHT') {
    return 'SOBRECOMPRA';
  }
  if (state === 'OVERSOLD') {
    return 'SOBREVENTA';
  }
  return 'Neutral';
}

function resolveSignalVisual(state) {
  const normalized = typeof state === 'string' ? state.trim().toUpperCase() : '';
  const known = SIGNAL_STATE_VISUALS[normalized];
  if (known) {
    return { ...known, rawState: normalized, isKnown: true };
  }

  return {
    label: 'Estado desconocido',
    interpretation: 'No se pudo clasificar el estado de la senal.',
    step: 0,
    chipClass: 'chip-neutral',
    rawState: normalized,
    isKnown: false,
  };
}

function resolveDirectionVisual(side) {
  const normalized = typeof side === 'string' ? side.trim().toUpperCase() : '';

  if (normalized === 'LONG' || normalized === 'SHORT') {
    return SIGNAL_DIRECTION_VISUALS[normalized];
  }

  if (!normalized || normalized === 'NEUTRAL' || normalized === 'NO TRADE' || normalized === 'NO_TRADE') {
    return SIGNAL_DIRECTION_VISUALS.NEUTRAL;
  }

  return {
    label: 'Direccion no disponible',
    arrow: '—',
    className: 'signal-direction-neutral',
  };
}

function setSignalChip(signalVisual) {
  const chip = byId('signal-state');
  chip.textContent = signalVisual.label;
  chip.classList.remove('chip-watch', 'chip-confirmed', 'chip-high', 'chip-very-high', 'chip-neutral');
  chip.classList.add(signalVisual.chipClass || 'chip-neutral');
}

function setSignalDirection(side) {
  const direction = resolveDirectionVisual(side);
  const container = byId('signal-direction');

  byId('signal-direction-arrow').textContent = direction.arrow;
  byId('signal-direction-label').textContent = direction.label;

  container.classList.remove('signal-direction-long', 'signal-direction-short', 'signal-direction-neutral');
  container.classList.add(direction.className || 'signal-direction-neutral');
}

function setSignalStepper(step) {
  const stepper = byId('signal-stepper');
  if (!stepper) {
    return;
  }

  const nodes = stepper.querySelectorAll('.signal-step');
  nodes.forEach((node) => {
    const nodeStep = Number(node.getAttribute('data-step'));
    node.classList.remove('signal-step-active', 'signal-step-done');

    if (step > 0 && Number.isFinite(nodeStep)) {
      if (nodeStep < step) {
        node.classList.add('signal-step-done');
      }
      if (nodeStep === step) {
        node.classList.add('signal-step-active');
      }
    }
  });
}

function clearTradePlan() {
  const badge = byId('plan-type-badge');
  if (badge) {
    badge.classList.add('hidden');
    badge.classList.remove('chip-high', 'chip-watch', 'chip-neutral');
    badge.textContent = '—';
  }
  byId('plan-side').textContent = '—';
  byId('plan-entry').textContent = '—';
  byId('plan-sl').textContent = '—';
  byId('plan-tp1').textContent = '—';
  byId('plan-tp2').textContent = '—';
  byId('plan-tp3').textContent = '—';
  byId('plan-rr1').textContent = '—';
  byId('plan-rr2').textContent = '—';
  byId('plan-rr3').textContent = '—';
  byId('plan-rrw').textContent = '—';
  byId('plan-margin').textContent = '—';
  byId('plan-leverage').textContent = '—';
  byId('plan-notional').textContent = '—';
  byId('plan-expected-r').textContent = '—';
}

function renderTradePlan(signalState, tradePlan, potentialPlan = null) {
  const container = byId('trade-plan');
  if (!container) {
    return;
  }

  const normalizedState = typeof signalState === 'string' ? signalState.trim().toUpperCase() : '';
  const isNoTrade = !normalizedState || normalizedState === 'NO_TRADE' || normalizedState === 'NO TRADE';

  if (isNoTrade) {
    container.classList.add('hidden');
    clearTradePlan();
    return;
  }

  const plan = tradePlan || potentialPlan;

  if (!plan) {
    container.classList.add('hidden');
    clearTradePlan();
    return;
  }

  container.classList.remove('hidden');

  const badge = byId('plan-type-badge');
  if (badge) {
    badge.classList.remove('hidden', 'chip-high', 'chip-watch', 'chip-neutral');
    if (tradePlan) {
      badge.textContent = 'PLAN OPERATIVO';
      badge.classList.add('chip-high');
    } else {
      badge.textContent = 'PLAN POTENCIAL';
      badge.classList.add('chip-watch');
    }
  }

  byId('plan-side').textContent = resolveDirectionVisual(plan.side).label;
  byId('plan-entry').textContent = asMoney(plan.entry);
  byId('plan-sl').textContent = asMoney(plan.sl);
  byId('plan-tp1').textContent = asMoney(plan.tp1);
  byId('plan-tp2').textContent = asMoney(plan.tp2);
  byId('plan-tp3').textContent = asMoney(plan.tp3);
  byId('plan-rr1').textContent = asNumber(plan.rr1, 2);
  byId('plan-rr2').textContent = asNumber(plan.rr2, 2);
  byId('plan-rr3').textContent = asNumber(plan.rr3, 2);
  byId('plan-rrw').textContent = asNumber(plan.weighted_rr, 2);
  byId('plan-margin').textContent = asMoney(plan.margin_usd);
  byId('plan-leverage').textContent = plan.leverage == null ? '—' : `${plan.leverage}x`;
  byId('plan-notional').textContent = asMoney(plan.notional_usd);
  byId('plan-expected-r').textContent = plan.expected_r == null ? 'N/A' : asNumber(plan.expected_r, 2);
}

function renderRange(price, swingRange) {
  const leftLabel = byId('range-label-left');
  if (leftLabel) {
    leftLabel.textContent = asMoney(swingRange.support);
  }
  const rightLabel = byId('range-label-right');
  if (rightLabel) {
    rightLabel.textContent = asMoney(swingRange.resistance);
  }
  const candlesUsed = byId('range-candles-used');
  if (candlesUsed) {
    const rawType = typeof swingRange?.display_type === 'string' ? swingRange.display_type.trim().toLowerCase() : '';
    const typeLabel = rawType === 'operational' ? 'RANGO OPERATIVO' : 'RANGO ESTRUCTURAL';
    const days = swingRange?.daily_candles_used ?? '—';
    candlesUsed.textContent = `${days}D / ${typeLabel}`;
  }

  const marker = byId('range-marker');
  if (marker) {
    const markerLeft = clamp(Number(swingRange.position_pct ?? 0), 0, 100);
    marker.style.left = `${markerLeft}%`;
  }
}

function renderSignal(signal) {
  const state = signal.state || 'NO_TRADE';
  const signalVisual = resolveSignalVisual(state);

  byId('signal-summary').textContent = signalVisual.interpretation;
  setSignalDirection(signal.side || null);
  setSignalStepper(signalVisual.step);

  const rrRow = byId('signal-rr-row');
  if (signal.weighted_rr == null) {
    rrRow.classList.add('hidden');
    byId('signal-rr').textContent = '';
  } else {
    rrRow.classList.remove('hidden');
    byId('signal-rr').textContent = asNumber(signal.weighted_rr, 2);
  }

  setSignalChip(signalVisual);
}

function renderDiagnosticsPivotList(listId, pivots) {
  const list = byId(listId);
  if (!list) {
    return;
  }

  list.replaceChildren();

  if (!Array.isArray(pivots) || pivots.length === 0) {
    const item = document.createElement('li');
    item.textContent = 'ninguno';
    list.appendChild(item);
    return;
  }

  const sortedPivots = [...pivots].sort((left, right) => {
    const leftTime = Date.parse(left?.timestamp || '');
    const rightTime = Date.parse(right?.timestamp || '');

    if (Number.isNaN(leftTime) && Number.isNaN(rightTime)) {
      return 0;
    }
    if (Number.isNaN(leftTime)) {
      return 1;
    }
    if (Number.isNaN(rightTime)) {
      return -1;
    }

    return rightTime - leftTime;
  });

  sortedPivots.forEach((pivot) => {
    const item = document.createElement('li');
    item.textContent = `${formatDayMonth(pivot.timestamp)} · ${asClusterMoney(pivot.price)}`;
    list.appendChild(item);
  });
}

function renderDiagnosticsSide(sidePayload, centerId, scoreId, pivotsId) {
  const centerElement = byId(centerId);
  const scoreElement = byId(scoreId);

  if (!sidePayload) {
    if (centerElement) {
      centerElement.textContent = '—';
    }
    if (scoreElement) {
      scoreElement.textContent = '—';
    }
    renderDiagnosticsPivotList(pivotsId, []);
    return;
  }

  if (centerElement) {
    centerElement.textContent = asClusterMoney(sidePayload.selected_level);
  }

  const scoreValue = Number.isFinite(Number(sidePayload.score)) ? Number(sidePayload.score) : null;
  if (scoreElement) {
    scoreElement.textContent = scoreValue == null ? '—' : String(scoreValue);
  }

  if (scoreValue === 0) {
    renderDiagnosticsPivotList(pivotsId, []);
    return;
  }

  renderDiagnosticsPivotList(pivotsId, sidePayload.pivots);
}

function renderTradeDiagnostics(tradeDiagnostics) {
  renderDiagnosticsSide(
    tradeDiagnostics?.resistance ?? null,
    'diag-resistance-center',
    'diag-resistance-score',
    'diag-resistance-pivots'
  );
  renderDiagnosticsSide(
    tradeDiagnostics?.support ?? null,
    'diag-support-center',
    'diag-support-score',
    'diag-support-pivots'
  );
}

function setTradeDiagnosticsExpanded(expanded) {
  const toggle = byId('trade-diagnostics-toggle');
  const chevron = byId('trade-diagnostics-chevron');
  const content = byId('trade-diagnostics-content');

  if (!toggle || !chevron || !content) {
    return;
  }

  toggle.setAttribute('aria-expanded', expanded ? 'true' : 'false');
  chevron.textContent = expanded ? '▲' : '▼';
  content.classList.toggle('hidden', !expanded);
}

function attachTradeDiagnosticsToggle() {
  const toggle = byId('trade-diagnostics-toggle');
  if (!toggle) {
    return;
  }

  setTradeDiagnosticsExpanded(false);

  toggle.addEventListener('click', () => {
    const isExpanded = toggle.getAttribute('aria-expanded') === 'true';
    setTradeDiagnosticsExpanded(!isExpanded);
  });
}

function hideHourlyVolumeTooltip() {
  const tooltip = byId('hourly-volume-tooltip');
  if (!tooltip) {
    return;
  }

  tooltip.classList.add('hidden');
}

function showHourlyVolumeTooltip(target) {
  const tooltip = byId('hourly-volume-tooltip');
  const plot = byId('hourly-volume-plot');
  if (!tooltip || !plot) {
    return;
  }

  const timeText = target.dataset.time || '—';
  const usdText = target.dataset.usd || '—';
  const btcText = target.dataset.btc || '';

  tooltip.replaceChildren();
  const timeNode = document.createElement('strong');
  timeNode.textContent = timeText;
  tooltip.appendChild(timeNode);
  for (const label of [usdText, ...(btcText ? [btcText + ' BTC'] : [])]) {
    const node = document.createElement('span');
    node.textContent = label;
    tooltip.appendChild(node);
  }
  tooltip.classList.remove('hidden');

  const plotRect = plot.getBoundingClientRect();
  const barRect = target.getBoundingClientRect();
  const rawLeft = barRect.left - plotRect.left + (barRect.width / 2);
  const left = clamp(rawLeft, 24, Math.max(24, plotRect.width - 24));
  tooltip.style.left = `${left}px`;
}

function renderHourlyVolumeChart(volume24hHourly) {
  const barsContainer = byId('hourly-volume-bars');
  const maxLabel = byId('hourly-volume-max');

  if (!barsContainer || !maxLabel) {
    return;
  }

  const bars = Array.isArray(volume24hHourly?.bars) ? volume24hHourly.bars : [];
  barsContainer.replaceChildren();
  hideHourlyVolumeTooltip();

  if (bars.length === 0) {
    maxLabel.textContent = 'MAX —';
    return;
  }

  const maxFromBars = Math.max(...bars.map((bar) => Number(bar.volume_usd) || 0), 0);
  const payloadMax = Number(volume24hHourly?.max_volume_usd);
  const maxUsd = payloadMax > 0 ? payloadMax : maxFromBars;
  const safeMaxUsd = Math.max(maxUsd, 1);

  maxLabel.textContent = `MAX ${asCompactUsd(maxUsd)}`;

  bars.forEach((bar, index) => {
    const volumeUsd = Math.max(0, Number(bar.volume_usd) || 0);
    const volumeBtc = Math.max(0, Number(bar.volume_btc) || 0);

    const barElement = document.createElement('button');
    barElement.type = 'button';
    barElement.className = 'hourly-volume-bar';

    const heightPct = (volumeUsd / safeMaxUsd) * 100;
    barElement.style.height = `${heightPct}%`;

    const tooltipTime = formatTimeFromIso(bar.timestamp);
    barElement.dataset.time = tooltipTime;
    barElement.dataset.usd = asCompactUsd(volumeUsd);
    barElement.dataset.btc = asCompactBtc(volumeBtc);
    barElement.title = `${tooltipTime}\n${barElement.dataset.usd}`;

    barElement.addEventListener('mouseenter', () => showHourlyVolumeTooltip(barElement));
    barElement.addEventListener('focus', () => showHourlyVolumeTooltip(barElement));
    barElement.addEventListener('click', (event) => {
      event.stopPropagation();
      showHourlyVolumeTooltip(barElement);
    });
    barElement.addEventListener('mouseleave', hideHourlyVolumeTooltip);
    barElement.addEventListener('blur', hideHourlyVolumeTooltip);

    barsContainer.appendChild(barElement);
  });
}

function renderMarket(market) {
  byId('price').textContent = asMoney(market.price);

  renderHourlyVolumeChart(market.volume_24h_hourly);

  const stoch = market.stoch_rsi_1h;
  byId('stoch').textContent = stoch ? `K ${asNumber(stoch.k, 0)} · D ${asNumber(stoch.d, 0)}` : '—';
  byId('stoch-state').textContent = stoch?.state ? mapStochStateLabel(stoch.state) : '—';
}

function setActiveView(viewName) {
  document.querySelectorAll('.view').forEach((view) => {
    view.classList.toggle('hidden', view.id !== `view-${viewName}`);
  });

  document.querySelectorAll('.nav-item').forEach((button) => {
    button.classList.toggle('active', button.dataset.view === viewName);
  });

  if (viewName === 'history') {
    void loadHistory();
    void loadPnlChart();
  }
}

function attachNavigation() {
  document.querySelectorAll('.nav-item').forEach((button) => {
    button.addEventListener('click', () => {
      setActiveView(button.dataset.view);
    });
  });
}

function historySideLabel(side) {
  const normalized = typeof side === 'string' ? side.trim().toUpperCase() : '';
  if (normalized === 'LONG') {
    return 'Largo';
  }
  if (normalized === 'SHORT') {
    return 'Corto';
  }
  return 'Neutral';
}

function historyStatusLabel(status) {
  const normalized = typeof status === 'string' ? status.trim().toUpperCase() : '';
  if (normalized === 'OPEN') {
    return 'Abierta';
  }
  if (normalized === 'CLOSED') {
    return 'Cerrada';
  }
  return normalized || '—';
}

function historyCloseResultLabel(status, events) {
  const normalizedStatus = typeof status === 'string' ? status.trim().toUpperCase() : '';
  if (normalizedStatus !== 'CLOSED') {
    return '';
  }

  const timeline = Array.isArray(events) ? events : [];
  if (timeline.length === 0) {
    return 'Cerrada';
  }

  const lastType = String(timeline[timeline.length - 1]?.event_type || '').toUpperCase();
  if (lastType === 'SL') {
    return 'Stop Loss';
  }
  if (lastType === 'TP1') {
    return 'TP1';
  }
  if (lastType === 'TP2') {
    return 'TP2';
  }
  if (lastType === 'TP3') {
    return 'TP3';
  }
  return 'Cerrada';
}

function historyEventTypeLabel(eventType) {
  const normalized = typeof eventType === 'string' ? eventType.trim().toUpperCase() : '';
  if (normalized === 'SL') {
    return 'Stop Loss';
  }
  if (normalized === 'TP1') {
    return 'TP1';
  }
  if (normalized === 'TP2') {
    return 'TP2';
  }
  if (normalized === 'TP3') {
    return 'TP3';
  }
  return normalized || 'Evento';
}

function historyValueClass(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric) || numeric === 0) {
    return '';
  }
  return numeric > 0 ? 'history-value-positive' : 'history-value-negative';
}

function buildHistoryMetric(label, value, valueClass = '') {
  const card = document.createElement('article');
  const labelElement = document.createElement('span');
  const valueElement = document.createElement('strong');

  labelElement.textContent = label;
  valueElement.textContent = value;
  if (valueClass) {
    valueElement.classList.add(valueClass);
  }

  card.append(labelElement, valueElement);
  return card;
}

function buildClosedTradeRow(label, value, valueClass = '') {
  const row = document.createElement('div');
  row.className = 'closed-trade-row';

  const labelElement = document.createElement('span');
  labelElement.className = 'closed-trade-label';
  labelElement.textContent = String(label).toUpperCase();

  const valueElement = document.createElement('strong');
  valueElement.className = 'closed-trade-value';
  valueElement.textContent = value;
  if (valueClass) {
    valueElement.classList.add(valueClass);
  }

  row.append(labelElement, valueElement);
  return row;
}

function buildHistoryEvents(trade) {
  const details = document.createElement('details');
  details.className = 'history-events';

  const events = Array.isArray(trade?.events) ? trade.events : [];
  const summary = document.createElement('summary');
  summary.textContent = `EVENTOS (${events.length})`;

  const timeline = document.createElement('ul');
  timeline.className = 'history-events-list';

  const createdItem = document.createElement('li');
  createdItem.className = 'history-event history-event-created';
  createdItem.textContent = `${formatHistoryDateTimeFromIso(trade.created_at)} · Operación creada`;
  timeline.appendChild(createdItem);

  events.forEach((event) => {
    const line = document.createElement('li');
    line.className = 'history-event';

    const parts = [
      formatHistoryDateTimeFromIso(event.event_at),
      historyEventTypeLabel(event.event_type),
    ];

    if (event.price != null && !Number.isNaN(Number(event.price))) {
      parts.push(asMoneyPrecise(event.price));
    }
    if (event.pnl_usd != null && !Number.isNaN(Number(event.pnl_usd))) {
      parts.push(asMoneyPrecise(event.pnl_usd));
    }
    if (event.fraction_closed != null && !Number.isNaN(Number(event.fraction_closed))) {
      parts.push(`${asNumber(Number(event.fraction_closed) * 100, 0)}%`);
    }

    line.textContent = parts.join(' · ');

    const pnlClass = historyValueClass(event.pnl_usd);
    if (pnlClass) {
      line.classList.add(pnlClass);
    }

    timeline.appendChild(line);
  });

  details.append(summary, timeline);
  return details;
}

function setHistoryFeedback(text, isError = false) {
  const feedback = byId('history-feedback');
  if (!feedback) {
    return;
  }

  feedback.textContent = text || '';
  feedback.classList.toggle('hidden', !text);
  feedback.classList.toggle('feedback-error', Boolean(text) && isError);
}

function setHistoryCount(count) {
  const badge = byId('history-count');
  if (!badge) {
    return;
  }

  const safeCount = Number.isFinite(Number(count)) ? Math.max(0, Number(count)) : 0;
  badge.textContent = safeCount === 1 ? '1 operación' : `${safeCount} operaciones`;
}

function renderHistory(items) {
  const list = byId('history-list');
  const empty = byId('history-empty');
  if (!list || !empty) {
    return;
  }

  list.replaceChildren();

  const historyItems = Array.isArray(items) ? items : [];
  if (historyItems.length === 0) {
    empty.textContent = 'No hay operaciones cerradas todavía.';
    empty.classList.remove('hidden');
    return;
  }

  empty.classList.add('hidden');

  historyItems.forEach((trade) => {
    const isClosed = String(trade.status || '').toUpperCase() === 'CLOSED';
    const sideLabel = historySideLabel(trade.side);
    const statusLabel = historyStatusLabel(trade.status);
    const closeLabel = historyCloseResultLabel(trade.status, trade.events);
    const realizedPnlClass = historyValueClass(trade.realized_pnl_usd);
    const realizedRClass = historyValueClass(trade.realized_r);

    const item = document.createElement('article');
    item.className = isClosed ? 'history-item history-item-closed' : 'history-item';

    const head = document.createElement('div');
    head.className = 'history-item-head';

    const date = document.createElement('p');
    date.className = 'history-item-time';
    date.textContent = formatHistoryDateTimeFromIso(trade.created_at);

    const badges = document.createElement('div');
    badges.className = 'history-item-badges';

    const sideBadge = document.createElement('span');
    sideBadge.className = 'history-badge history-badge-side';
    sideBadge.textContent = sideLabel;
    if (sideLabel === 'Largo') {
      sideBadge.classList.add('history-side-long');
    } else if (sideLabel === 'Corto') {
      sideBadge.classList.add('history-side-short');
    } else {
      sideBadge.classList.add('history-side-neutral');
    }

    const statusBadge = document.createElement('span');
    statusBadge.className = 'history-badge history-badge-status';
    statusBadge.textContent = closeLabel && closeLabel !== statusLabel ? `${statusLabel} · ${closeLabel}` : statusLabel;
    if (statusLabel === 'Abierta') {
      statusBadge.classList.add('history-status-open');
    } else {
      statusBadge.classList.add('history-status-closed');
    }

    badges.append(sideBadge, statusBadge);
    head.append(date, badges);

    const leverageValue = trade.leverage == null || Number.isNaN(Number(trade.leverage))
      ? '—'
      : `${Number(trade.leverage)}x`;
    const weightedRrValue = trade.weighted_rr == null || Number.isNaN(Number(trade.weighted_rr))
      ? '—'
      : asNumber(trade.weighted_rr, 2);
    const realizedRValue = trade.realized_r == null || Number.isNaN(Number(trade.realized_r))
      ? '—'
      : `${asNumber(trade.realized_r, 2)} R`;

    let bodyContent;
    if (isClosed) {
      bodyContent = document.createElement('div');
      bodyContent.className = 'closed-trade-details';
      bodyContent.append(
        buildClosedTradeRow('Entrada', asMoneyPrecise(trade.entry_reference)),
        buildClosedTradeRow('SL', asMoneyPrecise(trade.stop_loss)),
        buildClosedTradeRow('TP1', asMoneyPrecise(trade.tp1)),
        buildClosedTradeRow('TP2', asMoneyPrecise(trade.tp2)),
        buildClosedTradeRow('TP3', asMoneyPrecise(trade.tp3)),
        buildClosedTradeRow('Margen', asMoneyPrecise(trade.margin_usd)),
        buildClosedTradeRow('Apalancamiento', leverageValue),
        buildClosedTradeRow('RR', weightedRrValue),
        buildClosedTradeRow('PnL', asMoneyPrecise(trade.realized_pnl_usd), realizedPnlClass),
      );
    } else {
      bodyContent = document.createElement('div');
      bodyContent.className = 'history-metrics';
      bodyContent.append(
        buildHistoryMetric('Entrada', asMoneyPrecise(trade.entry_reference)),
        buildHistoryMetric('SL', asMoneyPrecise(trade.stop_loss)),
        buildHistoryMetric('TP1', asMoneyPrecise(trade.tp1)),
        buildHistoryMetric('TP2', asMoneyPrecise(trade.tp2)),
        buildHistoryMetric('TP3', asMoneyPrecise(trade.tp3)),
        buildHistoryMetric('Margen', asMoneyPrecise(trade.margin_usd)),
        buildHistoryMetric('Apalancamiento', leverageValue),
        buildHistoryMetric('RR', weightedRrValue),
        buildHistoryMetric('PnL', asMoneyPrecise(trade.realized_pnl_usd), realizedPnlClass),
      );
    }

    item.append(head, bodyContent, buildHistoryEvents(trade));
    list.appendChild(item);
  });
}

async function loadHistory(limit = 100) {
  if (historyRefreshInFlight) {
    return;
  }

  historyRefreshInFlight = true;
  const list = byId('history-list');
  const empty = byId('history-empty');

  try {
    setHistoryFeedback('');

    const response = await fetch(`/api/history?limit=${encodeURIComponent(limit)}`, { cache: 'no-store' });
    if (!response.ok) {
      throw new Error('No fue posible obtener el histórico.');
    }

    const payload = await response.json();
    const items = Array.isArray(payload?.items) ? payload.items : [];

    setHistoryCount(items.length);
    renderHistory(items);
  } catch (error) {
    if (list) {
      list.replaceChildren();
    }
    if (empty) {
      empty.classList.add('hidden');
    }
    setHistoryCount(0);
    setHistoryFeedback('No se pudo cargar el histórico.', true);
    console.error(error);
  } finally {
    historyRefreshInFlight = false;
  }
}

let pnlChartInFlight = false;

function hidePnlTooltip() {
  const tooltip = byId('pnl-chart-tooltip');
  if (tooltip) {
    tooltip.classList.add('hidden');
  }
}

function showPnlTooltip(target, point) {
  const tooltip = byId('pnl-chart-tooltip');
  const plot = byId('pnl-chart-plot');
  if (!tooltip || !plot || !point) {
    return;
  }

  const pnlUsd = Number(point.daily_pnl) || 0;
  const cumPnlUsd = Number(point.cumulative_pnl) || 0;
  const count = Number(point.trade_count) || 0;
  const sign = pnlUsd > 0 ? '+' : '';
  const cumSign = cumPnlUsd > 0 ? '+' : '';

  tooltip.replaceChildren();
  const dateNode = document.createElement('strong');
  dateNode.textContent = String(point.date ?? '') + ' (UTC)';
  tooltip.appendChild(dateNode);
  for (const [label, value] of [
    ['PnL diario: ', sign + asMoneyPrecise(pnlUsd)],
    ['PnL acumulado: ', cumSign + asMoneyPrecise(cumPnlUsd)],
    ['Operaciones cerradas: ', String(count)],
  ]) {
    const span = document.createElement('span');
    span.textContent = label;
    const strong = document.createElement('strong');
    strong.textContent = value;
    span.appendChild(strong);
    tooltip.appendChild(span);
  }
  tooltip.classList.remove('hidden');

  const plotRect = plot.getBoundingClientRect();
  let rawLeft = plotRect.width / 2;
  if (typeof target === 'number') {
    rawLeft = target;
  } else if (target && typeof target.getBoundingClientRect === 'function') {
    const dotRect = target.getBoundingClientRect();
    rawLeft = dotRect.left - plotRect.left + (dotRect.width / 2);
  }
  const left = clamp(rawLeft, 60, Math.max(60, plotRect.width - 60));
  tooltip.style.left = `${left}px`;
}

function renderPnlChart(points, days) {
  const svg = byId('pnl-chart-svg');
  const empty = byId('pnl-chart-empty');
  const summary = byId('pnl-chart-summary');

  if (!svg || !empty) {
    return;
  }

  svg.replaceChildren();
  hidePnlTooltip();

  const dataPoints = Array.isArray(points) ? points : [];
  if (dataPoints.length === 0) {
    svg.classList.add('hidden');
    empty.classList.remove('hidden');
    if (summary) {
      summary.textContent = '—';
      summary.className = 'chip chip-neutral';
    }
    return;
  }

  svg.classList.remove('hidden');
  empty.classList.add('hidden');

  const lastPoint = dataPoints[dataPoints.length - 1];
  const totalPnl = Number(lastPoint?.cumulative_pnl) || 0;
  if (summary) {
    const prefix = totalPnl > 0 ? '+' : '';
    summary.textContent = `${prefix}${asMoneyPrecise(totalPnl)} USD`;
    summary.className = 'chip';
    if (totalPnl > 0) {
      summary.classList.add('chip-high');
    } else if (totalPnl < 0) {
      summary.classList.add('signal-direction-short');
    } else {
      summary.classList.add('chip-neutral');
    }
  }

  const svgWidth = 800;
  const svgHeight = 260;
  svg.setAttribute('viewBox', `0 0 ${svgWidth} ${svgHeight}`);
  svg.setAttribute('preserveAspectRatio', 'none');

  const padLeft = 70;
  const padRight = 30;
  const padTop = 25;
  const padBottom = 40;
  const plotWidth = svgWidth - padLeft - padRight;
  const plotHeight = svgHeight - padTop - padBottom;

  const cumValues = dataPoints.map((p) => Number(p.cumulative_pnl) || 0);
  const minVal = Math.min(...cumValues);
  const maxVal = Math.max(...cumValues);

  let yMin, yMax;
  if (minVal === maxVal) {
    const offset = Math.abs(minVal) > 0 ? Math.abs(minVal) * 0.1 : 10;
    yMin = minVal - offset;
    yMax = maxVal + offset;
  } else {
    const span = maxVal - minVal;
    const padding = span * 0.15;
    yMin = minVal - padding;
    yMax = maxVal + padding;
  }

  const yRange = yMax - yMin;

  function getX(index) {
    if (dataPoints.length === 1) {
      return padLeft + plotWidth / 2;
    }
    return padLeft + (index / (dataPoints.length - 1)) * plotWidth;
  }

  function getY(val) {
    return padTop + plotHeight - ((val - yMin) / yRange) * plotHeight;
  }

  // Draw horizontal grid lines & Y labels (4 lines)
  const numTicks = 4;
  for (let t = 0; t <= numTicks; t++) {
    const tickVal = yMin + (t / numTicks) * yRange;
    const tickY = getY(tickVal);

    const gridLine = document.createElementNS('http://www.w3.org/2000/svg', 'line');
    gridLine.setAttribute('x1', String(padLeft));
    gridLine.setAttribute('x2', String(padLeft + plotWidth));
    gridLine.setAttribute('y1', String(tickY));
    gridLine.setAttribute('y2', String(tickY));
    gridLine.setAttribute('stroke', '#1e293b');
    gridLine.setAttribute('stroke-width', '1');
    svg.appendChild(gridLine);

    const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    text.setAttribute('x', String(padLeft - 10));
    text.setAttribute('y', String(tickY + 4));
    text.setAttribute('text-anchor', 'end');
    text.setAttribute('fill', '#72829a');
    text.setAttribute('font-size', '11');
    text.setAttribute('font-family', 'sans-serif');
    text.textContent = asMoney(tickVal);
    svg.appendChild(text);
  }

  // Draw zero baseline if 0 is between yMin and yMax
  if (yMin <= 0 && yMax >= 0) {
    const zeroY = getY(0);
    const zeroLine = document.createElementNS('http://www.w3.org/2000/svg', 'line');
    zeroLine.setAttribute('x1', String(padLeft));
    zeroLine.setAttribute('x2', String(padLeft + plotWidth));
    zeroLine.setAttribute('y1', String(zeroY));
    zeroLine.setAttribute('y2', String(zeroY));
    zeroLine.setAttribute('stroke', '#475569');
    zeroLine.setAttribute('stroke-width', '1.5');
    zeroLine.setAttribute('stroke-dasharray', '4 4');
    svg.appendChild(zeroLine);
  }

  // Construct stepped (zero-order hold) line path coordinates
  const coords = dataPoints.map((p, i) => ({
    x: getX(i),
    y: getY(Number(p.cumulative_pnl) || 0),
    point: p,
  }));

  let d = '';
  coords.forEach((c, i) => {
    if (i === 0) {
      d = `M ${c.x.toFixed(1)} ${c.y.toFixed(1)}`;
    } else {
      const prev = coords[i - 1];
      d += ` L ${c.x.toFixed(1)} ${prev.y.toFixed(1)} L ${c.x.toFixed(1)} ${c.y.toFixed(1)}`;
    }
  });

  const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
  path.setAttribute('d', d);
  path.setAttribute('fill', 'none');
  path.setAttribute('stroke', '#ffffff');
  path.setAttribute('stroke-width', '2');
  path.setAttribute('stroke-linejoin', 'miter');
  path.setAttribute('stroke-linecap', 'square');
  svg.appendChild(path);

  // Draw X-axis date labels
  const labelIndices = [0];
  if (dataPoints.length > 2) {
    labelIndices.push(Math.floor((dataPoints.length - 1) / 2));
  }
  if (dataPoints.length > 1) {
    labelIndices.push(dataPoints.length - 1);
  }

  labelIndices.forEach((idx) => {
    const p = dataPoints[idx];
    const x = getX(idx);
    const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    text.setAttribute('x', String(x));
    text.setAttribute('y', String(padTop + plotHeight + 22));
    text.setAttribute('text-anchor', idx === 0 ? 'start' : idx === dataPoints.length - 1 ? 'end' : 'middle');
    text.setAttribute('fill', '#8c9bb2');
    text.setAttribute('font-size', '11');
    text.setAttribute('font-family', 'sans-serif');
    text.textContent = formatWindowDate(p.date);
    svg.appendChild(text);
  });

  // Tooltip tracking via mousemove across SVG (ZERO circle elements generated)
  svg.onmousemove = (e) => {
    if (dataPoints.length === 0) {
      return;
    }
    const plot = byId('pnl-chart-plot');
    if (!plot) {
      return;
    }
    const plotRect = plot.getBoundingClientRect();
    const svgRect = svg.getBoundingClientRect();
    if (svgRect.width <= 0) {
      return;
    }

    const svgX = ((e.clientX - svgRect.left) / svgRect.width) * svgWidth;
    if (svgX < padLeft || svgX > padLeft + plotWidth) {
      hidePnlTooltip();
      return;
    }

    const ratio = clamp((svgX - padLeft) / plotWidth, 0, 1);
    const idx = clamp(Math.round(ratio * (dataPoints.length - 1)), 0, dataPoints.length - 1);
    const point = dataPoints[idx];
    const targetX = (getX(idx) / svgWidth) * plotRect.width;
    showPnlTooltip(targetX, point);
  };

  svg.onmouseleave = () => {
    hidePnlTooltip();
  };
}

async function loadPnlChart(days = null) {
  if (pnlChartInFlight) {
    return;
  }

  pnlChartInFlight = true;
  try {
    const url = days ? `/api/pnl/daily-cumulative?days=${encodeURIComponent(days)}` : '/api/pnl/daily-cumulative';
    const response = await fetch(url, { cache: 'no-store' });
    if (!response.ok) {
      throw new Error('No fue posible obtener la serie de PnL.');
    }

    const payload = await response.json();
    const points = Array.isArray(payload?.points) ? payload.points : [];
    const activeDays = Number(payload?.days) || days || 30;

    renderPnlChart(points, activeDays);
  } catch (error) {
    console.error(error);
  } finally {
    pnlChartInFlight = false;
  }
}

function attachDatabaseReset() {
  const openButton = byId('database-reset-button');
  const modal = byId('reset-confirm-modal');
  const cancelButton = byId('reset-modal-cancel');
  const confirmButton = byId('reset-modal-confirm');
  const backdrop = modal?.querySelector('.modal-backdrop');
  const feedback = byId('database-reset-feedback');

  if (!openButton || !modal || !cancelButton || !confirmButton) {
    return;
  }

  function openModal() {
    modal.classList.remove('hidden');
    if (feedback) {
      feedback.textContent = '';
      feedback.className = 'form-feedback';
    }
  }

  function closeModal() {
    modal.classList.add('hidden');
  }

  openButton.addEventListener('click', () => {
    openModal();
  });

  cancelButton.addEventListener('click', () => {
    closeModal();
  });

  if (backdrop) {
    backdrop.addEventListener('click', () => {
      closeModal();
    });
  }

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && !modal.classList.contains('hidden')) {
      closeModal();
    }
  });

  confirmButton.addEventListener('click', async () => {
    confirmButton.disabled = true;
    confirmButton.textContent = 'Reseteando...';

    try {
      const response = await fetch('/api/database/reset', {
        method: 'POST',
        headers: getCsrfHeaders(),
      });

      if (!response.ok) {
        if (response.status === 403) {
          closeModal();
          if (feedback) {
            feedback.textContent = 'Permiso denegado: acción exclusiva de administradores.';
            feedback.className = 'form-feedback feedback-error';
          }
          return;
        }
        throw new Error('Database reset failed');
      }

      const payload = await response.json();
      if (!payload?.ok) {
        throw new Error('Database reset failed');
      }

      closeModal();
      if (feedback) {
        feedback.textContent = '✓ Base de datos reseteada correctamente.';
        feedback.className = 'form-feedback feedback-success';
      }

      await refreshDashboard({ scheduleNext: false });
      await loadHistory();
      await loadPnlChart();
    } catch (err) {
      closeModal();
      if (feedback) {
        feedback.textContent = '✕ No fue posible resetear la base de datos.';
        feedback.className = 'form-feedback feedback-error';
      }
      console.error(err);
    } finally {
      confirmButton.disabled = false;
      confirmButton.textContent = 'Resetear base de datos';
    }
  });
}

function setSettingsFeedback(text, type = 'info') {
  const feedback = byId('settings-feedback');
  if (!feedback) {
    return;
  }

  feedback.textContent = text;
  feedback.classList.remove('feedback-success', 'feedback-error');

  if (type === 'success') {
    feedback.classList.add('feedback-success');
  }
  if (type === 'error') {
    feedback.classList.add('feedback-error');
  }
}

function setAutomationStatusBadge(isRunning) {
  const statusBadge = byId('automation-status-badge');
  const statusText = byId('automation-status-text');

  if (!statusBadge || !statusText) {
    return;
  }

  statusBadge.classList.remove(
    'automation-status-neutral',
    'automation-status-active',
    'automation-status-inactive',
  );

  if (isRunning) {
    statusText.textContent = 'Activo';
    statusBadge.classList.add('automation-status-active');
    return;
  }

  statusText.textContent = 'Inactivo';
  statusBadge.classList.add('automation-status-inactive');
}

function setAutomationField(id, value) {
  const element = byId(id);
  if (!element) {
    return;
  }
  element.textContent = value || '—';
}

function setAutomationStaleWarning(isVisible) {
  const warning = byId('automation-stale-warning');
  if (!warning) {
    return;
  }
  warning.classList.toggle('hidden', !isVisible);
}

function formatIntervalLabel(intervalSeconds) {
  const interval = Number(intervalSeconds);
  if (!Number.isFinite(interval) || interval <= 0) {
    return '—';
  }
  if (interval % 60 === 0) {
    return `${interval / 60} min`;
  }
  return `${interval} s`;
}

function isAutomationStale(lastMarketCycleAt) {
  if (!lastMarketCycleAt) {
    return false;
  }

  const cycleDate = new Date(lastMarketCycleAt);
  if (Number.isNaN(cycleDate.getTime())) {
    return false;
  }

  return (Date.now() - cycleDate.getTime()) > AUTOMATION_STALE_THRESHOLD_MS;
}

function renderAutomationStatus(payload) {
  const running = Boolean(payload?.running);
  setAutomationStatusBadge(running);

  setAutomationField('automation-interval', formatIntervalLabel(payload?.interval_seconds));
  setAutomationField('automation-last-cycle', formatTimeFromIso(payload?.last_market_cycle_at || null));
  setAutomationField('automation-next-cycle', formatTimeFromIso(payload?.next_market_cycle_at || null));

  const stale = running && (Boolean(payload?.is_stale) || isAutomationStale(payload?.last_market_cycle_at || null));
  setAutomationStaleWarning(stale);
}

async function loadAutomationStatus() {
  const response = await fetch('/api/automation/status', { cache: 'no-store' });
  if (!response.ok) {
    throw new Error('No fue posible obtener el estado del motor automático.');
  }

  const payload = await response.json();
  renderAutomationStatus(payload);
  return payload;
}

function setTelegramFeedback(text, type = 'info') {
  const feedback = byId('telegram-feedback');
  if (!feedback) {
    return;
  }

  feedback.textContent = text;
  feedback.classList.remove('feedback-success', 'feedback-error');

  if (type === 'success') {
    feedback.classList.add('feedback-success');
  }
  if (type === 'error') {
    feedback.classList.add('feedback-error');
  }
}

function setTelegramButtonBusy(isBusy) {
  const button = byId('telegram-test-button');
  if (!button) {
    return;
  }

  button.disabled = isBusy;
  button.textContent = isBusy ? TELEGRAM_TEST_BUSY_TEXT : TELEGRAM_TEST_IDLE_TEXT;
}

function setTelegramStatusBadge(enabled, configured) {
  const statusBadge = byId('telegram-status-badge');
  const statusText = byId('telegram-status-text');

  if (!statusBadge || !statusText) {
    return;
  }

  statusBadge.classList.remove(
    'telegram-status-neutral',
    'telegram-status-configured',
    'telegram-status-not-configured',
    'telegram-status-disabled',
  );

  if (!enabled) {
    statusText.textContent = 'Deshabilitado';
    statusBadge.classList.add('telegram-status-disabled');
    return;
  }

  if (configured) {
    statusText.textContent = 'Configurado';
    statusBadge.classList.add('telegram-status-configured');
    return;
  }

  statusText.textContent = 'No configurado';
  statusBadge.classList.add('telegram-status-not-configured');
}

function setTelegramLastTest(lastTestAt) {
  const lastTest = byId('telegram-last-test');
  if (!lastTest) {
    return;
  }
  lastTest.textContent = formatDateTimeFromIso(lastTestAt);
}

async function loadTelegramStatus() {
  const response = await fetch('/api/telegram/status', { cache: 'no-store' });
  if (!response.ok) {
    throw new Error('No fue posible obtener el estado de Telegram.');
  }

  const payload = await response.json();
  setTelegramStatusBadge(Boolean(payload.enabled), Boolean(payload.configured));
  setTelegramLastTest(payload.last_test_at || null);
  return payload;
}

async function sendTelegramTest() {
  setTelegramFeedback('');
  setTelegramButtonBusy(true);

  try {
    const response = await fetch('/api/telegram/test', {
      method: 'POST',
      headers: getCsrfHeaders(),
    });

    if (!response.ok) {
      if (response.status === 403) {
        setTelegramFeedback('Permiso denegado: acción exclusiva de administradores.', 'error');
        return;
      }
      throw new Error('Telegram test failed');
    }

    const payload = await response.json();
    if (!payload?.ok) {
      throw new Error('Telegram test failed');
    }

    setTelegramFeedback('✓ Mensaje enviado correctamente', 'success');

    const status = await loadTelegramStatus().catch(() => null);
    if (!status?.last_test_at) {
      setTelegramLastTest(new Date().toISOString());
    }
  } catch (_error) {
    setTelegramFeedback('✕ No se pudo enviar el mensaje', 'error');
  } finally {
    setTelegramButtonBusy(false);
  }
}

function parseAndValidateSetting(key, value) {
  const limits = SETTINGS_LIMITS[key];
  const raw = value == null ? '' : String(value).trim();
  if (!raw) {
    throw new Error(`${limits.label}: introduce un valor.`);
  }

  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    throw new Error(`${limits.label}: introduce un número válido.`);
  }

  if (limits.type === 'int' && !Number.isInteger(numeric)) {
    throw new Error(`${limits.label}: introduce un número entero.`);
  }
  if (numeric < limits.min || numeric > limits.max) {
    throw new Error(`${limits.label}: el valor debe estar entre ${limits.min} y ${limits.max}.`);
  }

  return limits.type === 'int' ? Math.trunc(numeric) : numeric;
}

async function loadSettings() {
  const response = await fetch('/api/settings', { cache: 'no-store' });
  if (!response.ok) {
    throw new Error(await response.text());
  }

  const payload = await response.json();
  if (byId('daily-swing-candles')) {
    byId('daily-swing-candles').value = payload.daily_swing_candles;
  }
  byId('backtest-candles').value = payload.backtest_candles;
  byId('lookback-days').value = payload.lookback_days;
  byId('pivot-left').value = payload.pivot_left;
  byId('pivot-right').value = payload.pivot_right;
  byId('min-confirmations').value = payload.min_confirmations;
  byId('cluster-tolerance-pct').value = payload.cluster_tolerance_pct;
  byId('sma20-filter-pct').value = payload.sma20_filter_pct;
  byId('operational-range-pct').value = payload.operational_range_pct;
  if (byId('min-operational-range-pct')) {
    byId('min-operational-range-pct').value = payload.min_operational_range_pct;
  }
  if (byId('pnl-chart-days')) {
    byId('pnl-chart-days').value = String(payload.pnl_chart_days ?? 30);
  }
  if (byId('volume-baseline-period') && payload.volume_baseline_period != null) {
    byId('volume-baseline-period').value = payload.volume_baseline_period;
  }
  if (byId('volume-confirmation-threshold') && payload.volume_confirmation_threshold != null) {
    byId('volume-confirmation-threshold').value = payload.volume_confirmation_threshold;
  }
}

function scheduleNextRefresh() {
  if (refreshTimer) {
    clearTimeout(refreshTimer);
  }

  refreshTimer = setTimeout(() => {
    void refreshDashboard();
  }, refreshIntervalMs);
}

async function refreshDashboard(options = { scheduleNext: true }) {
  if (refreshInFlight) {
    return;
  }

  refreshInFlight = true;

  try {
    const response = await fetch('/api/dashboard', { cache: 'no-store' });
    if (!response.ok) {
      throw new Error(await response.text());
    }

    const payload = await response.json();
    if (Number(payload.refresh_interval_seconds) > 0) {
      refreshIntervalMs = Number(payload.refresh_interval_seconds) * 1000;
    }

    renderMarket(payload.market || {});
    renderRange(payload.market?.price, payload.swing_range);
    renderSignal(payload.signal || {});
    renderTradePlan(payload.signal?.state, payload.trade_plan, payload.potential_trade_plan);
    renderTradeDiagnostics(payload.trade_diagnostics || null);

    lastValidTimestampIso = payload.timestamp || lastValidTimestampIso;
    byId('status').textContent = 'ONLINE';
    byId('updated-at').textContent = `Actualizado ${formatTimeFromIso(lastValidTimestampIso)}`;

    try {
      await loadAutomationStatus();
    } catch (error) {
      console.error(error);
    }

    const historyView = byId('view-history');
    if (historyView && !historyView.classList.contains('hidden')) {
      await loadHistory();
      await loadPnlChart();
    }
  } catch (error) {
    byId('status').textContent = 'Datos temporalmente no actualizados';
    const fallback = lastValidTimestampIso
      ? `Última actualización válida: ${formatTimeFromIso(lastValidTimestampIso)}`
      : 'Datos temporalmente no actualizados';
    byId('updated-at').textContent = fallback;
    console.error(error);
  } finally {
    refreshInFlight = false;
    if (options.scheduleNext !== false) {
      scheduleNextRefresh();
    }
  }
}

async function saveSettings(event) {
  event.preventDefault();

  try {
    const dailySwingEl = byId('daily-swing-candles');
    const dailySwing = dailySwingEl ? parseAndValidateSetting('daily_swing_candles', dailySwingEl.value) : undefined;
    const backtest = parseAndValidateSetting('backtest_candles', byId('backtest-candles').value);
    const lookbackDays = parseAndValidateSetting('lookback_days', byId('lookback-days').value);
    const pivotLeft = parseAndValidateSetting('pivot_left', byId('pivot-left').value);
    const pivotRight = parseAndValidateSetting('pivot_right', byId('pivot-right').value);
    const minConfirmations = parseAndValidateSetting('min_confirmations', byId('min-confirmations').value);
    const clusterTolerancePct = parseAndValidateSetting('cluster_tolerance_pct', byId('cluster-tolerance-pct').value);
    const sma20FilterPct = parseAndValidateSetting('sma20_filter_pct', byId('sma20-filter-pct').value);
    const operationalRangePct = parseAndValidateSetting('operational_range_pct', byId('operational-range-pct').value);
    const minOperationalRangePct = parseAndValidateSetting('min_operational_range_pct', byId('min-operational-range-pct').value);
    const pnlChartDays = parseAndValidateSetting('pnl_chart_days', byId('pnl-chart-days').value);
    const volumeBaselinePeriod = byId('volume-baseline-period')
      ? parseAndValidateSetting('volume_baseline_period', byId('volume-baseline-period').value)
      : undefined;
    const volumeConfirmationThreshold = byId('volume-confirmation-threshold')
      ? parseAndValidateSetting('volume_confirmation_threshold', byId('volume-confirmation-threshold').value)
      : undefined;

    const bodyPayload = {
      backtest_candles: backtest,
      lookback_days: lookbackDays,
      pivot_left: pivotLeft,
      pivot_right: pivotRight,
      min_confirmations: minConfirmations,
      cluster_tolerance_pct: clusterTolerancePct,
      sma20_filter_pct: sma20FilterPct,
      operational_range_pct: operationalRangePct,
      min_operational_range_pct: minOperationalRangePct,
      pnl_chart_days: pnlChartDays,
    };
    if (dailySwing !== undefined) {
      bodyPayload.daily_swing_candles = dailySwing;
    }
    if (volumeBaselinePeriod !== undefined) {
      bodyPayload.volume_baseline_period = volumeBaselinePeriod;
    }
    if (volumeConfirmationThreshold !== undefined) {
      bodyPayload.volume_confirmation_threshold = volumeConfirmationThreshold;
    }

    const response = await fetch('/api/settings', {
      method: 'PUT',
      headers: getCsrfHeaders({
        'Content-Type': 'application/json',
      }),
      body: JSON.stringify(bodyPayload),
    });

    if (!response.ok) {
      if (response.status === 403) {
        setSettingsFeedback('Permiso denegado: acción exclusiva de administradores.', 'error');
        return;
      }
      const errorBody = await response.json().catch(() => null);
      const detail = errorBody?.detail || 'No fue posible guardar ajustes.';
      throw new Error(String(detail));
    }

    const saved = await response.json();
    if (byId('daily-swing-candles') && saved.daily_swing_candles != null) {
      byId('daily-swing-candles').value = saved.daily_swing_candles;
    }
    byId('backtest-candles').value = saved.backtest_candles;
    byId('lookback-days').value = saved.lookback_days;
    byId('pivot-left').value = saved.pivot_left;
    byId('pivot-right').value = saved.pivot_right;
    byId('min-confirmations').value = saved.min_confirmations;
    byId('cluster-tolerance-pct').value = saved.cluster_tolerance_pct;
    byId('sma20-filter-pct').value = saved.sma20_filter_pct;
    byId('operational-range-pct').value = saved.operational_range_pct;
    if (byId('min-operational-range-pct')) {
      byId('min-operational-range-pct').value = saved.min_operational_range_pct;
    }
    if (byId('pnl-chart-days')) {
      byId('pnl-chart-days').value = String(saved.pnl_chart_days ?? 30);
    }
    if (byId('volume-baseline-period') && saved.volume_baseline_period != null) {
      byId('volume-baseline-period').value = saved.volume_baseline_period;
    }
    if (byId('volume-confirmation-threshold') && saved.volume_confirmation_threshold != null) {
      byId('volume-confirmation-threshold').value = saved.volume_confirmation_threshold;
    }
    setSettingsFeedback('Ajustes guardados correctamente', 'success');

    await refreshDashboard({ scheduleNext: false });
    await loadPnlChart(saved.pnl_chart_days);
    scheduleNextRefresh();
  } catch (error) {
    setSettingsFeedback(error instanceof Error ? error.message : 'Error guardando ajustes', 'error');
  }
}

function attachSettingsForm() {
  const form = byId('settings-form');
  if (!form) {
    return;
  }
  form.addEventListener('submit', saveSettings);
}

function attachTelegramTestButton() {
  const button = byId('telegram-test-button');
  if (!button) {
    return;
  }

  button.addEventListener('click', () => {
    void sendTelegramTest();
  });
}

let currentUser = null;

async function checkAuth() {
  // Android may kill the PWA process and momentarily lose connectivity on restart.
  // Only an explicit authentication rejection proves the session is invalid.
  function showReconnect() {
    let notice = document.getElementById('auth-reconnect');
    if (notice) return;
    notice = document.createElement('div');
    notice.id = 'auth-reconnect';
    notice.setAttribute('role', 'alert');
    notice.style.cssText = 'position:fixed;z-index:99999;inset:0;background:#101827;color:#fff;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:16px;padding:24px;text-align:center';
    const message = document.createElement('p');
    message.textContent = 'No se pudo verificar la sesión. Comprueba la conexión; no es necesario volver a introducir la contraseña.';
    const retry = document.createElement('button');
    retry.type = 'button';
    retry.textContent = 'Reintentar conexión';
    retry.addEventListener('click', () => { notice.remove(); void bootstrap(); });
    notice.append(message, retry);
    document.body.append(notice);
  }
  try {
    const res = await fetch('/api/auth/me', { cache: 'no-store', credentials: 'same-origin' });
    if (res.status === 401 || res.status === 403) {
      window.location.replace('/login');
      return null;
    }
    if (!res.ok) {
      showReconnect();
      return null;
    }
    const user = await res.json();
    document.getElementById('auth-reconnect')?.remove();
    currentUser = user;
    renderAuthBar(user);
    applyRbacUI(user);
    return user;
  } catch (err) {
    console.warn('Verificación de sesión temporalmente no disponible.');
    showReconnect();
    return null;
  }
}

let currentCsrfToken = null;

async function fetchCsrfToken() {
  try {
    const res = await fetch('/api/auth/csrf');
    if (res.ok) {
      const data = await res.json();
      currentCsrfToken = data.csrf_token || null;
      return currentCsrfToken;
    }
  } catch (err) {
    console.error('Failed to fetch CSRF token:', err);
  }
  return null;
}

function getCsrfHeaders(extraHeaders = {}) {
  const headers = { ...extraHeaders };
  if (currentCsrfToken) {
    headers['X-CSRF-Token'] = currentCsrfToken;
  }
  return headers;
}

function renderAuthBar(user) {
  const authBar = byId('auth-bar');
  const authUser = byId('auth-user');
  const logoutBtn = byId('logout-btn');
  if (authBar && authUser) {
    authBar.classList.remove('hidden');
    authUser.textContent = `${user.username} (${user.role})`;
  }
  if (logoutBtn && !logoutBtn.dataset.bound) {
    logoutBtn.dataset.bound = 'true';
    logoutBtn.addEventListener('click', async () => {
      try {
        await fetch('/api/auth/logout', {
          method: 'POST',
          headers: getCsrfHeaders(),
        });
      } finally {
        window.location.href = '/login';
      }
    });
  }
}

function applyRbacUI(user) {
  if (user.role === 'VIEWER') {
    const saveSettingsBtn = byId('save-settings');
    if (saveSettingsBtn) {
      saveSettingsBtn.disabled = true;
      saveSettingsBtn.title = 'Acción restringida a administradores';
      saveSettingsBtn.style.opacity = '0.5';
      saveSettingsBtn.style.cursor = 'not-allowed';
    }
    const telegramTestBtn = byId('telegram-test-button');
    if (telegramTestBtn) {
      telegramTestBtn.disabled = true;
      telegramTestBtn.title = 'Acción restringida a administradores';
      telegramTestBtn.style.opacity = '0.5';
      telegramTestBtn.style.cursor = 'not-allowed';
    }
    const dbResetBtn = byId('database-reset-button');
    if (dbResetBtn) {
      dbResetBtn.disabled = true;
      dbResetBtn.title = 'Acción restringida a administradores';
      dbResetBtn.style.opacity = '0.5';
      dbResetBtn.style.cursor = 'not-allowed';
    }
    const settingsInputs = document.querySelectorAll('#settings-form input, #settings-form select');
    settingsInputs.forEach(input => {
      input.disabled = true;
    });
  }
}

function attachPasswordChange() {
  const form = byId('password-change-form');
  const feedback = byId('password-change-feedback');
  const button = byId('password-change-submit');
  if (!form || !feedback || !button) return;
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const current = byId('password-current').value;
    const next = byId('password-new').value;
    const confirm = byId('password-confirm').value;
    feedback.textContent = '';
    if (!current || next.length < 16 || next.length > 256 || next !== confirm || current === next) {
      feedback.textContent = 'Comprueba la contraseña actual, la confirmación y el mínimo de 16 caracteres.';
      return;
    }
    button.disabled = true;
    try {
      const response = await fetch('/api/auth/change-password', {
        method: 'POST',
        credentials: 'same-origin',
        headers: getCsrfHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ current_password: current, new_password: next }),
      });
      if (response.status === 401) {
        window.location.assign('/login');
        return;
      }
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        feedback.textContent = data.detail || 'No se pudo cambiar la contraseña.';
        return;
      }
      form.reset();
      currentCsrfToken = null;
      feedback.textContent = 'Contraseña actualizada. Cerrando sesiones...';
      window.location.assign('/login');
    } catch (_) {
      feedback.textContent = 'No se pudo conectar con el servidor.';
    } finally {
      button.disabled = false;
    }
  });
}

function attachRecoveryCodes() {
  const form = byId('recovery-generate-form');
  const remaining = byId('recovery-remaining');
  const generated = byId('recovery-generated');
  const output = byId('recovery-codes-output');
  const message = byId('recovery-generate-feedback');
  const button = byId('recovery-generate-button');
  if (!form || !remaining || !generated || !output || !message || !button) return;
  const clearDisplay = () => {
    output.textContent = '';
    generated.classList.add('hidden');
  };
  const refresh = async () => {
    const r = await fetch('/api/auth/recovery-codes/status', { cache: 'no-store' });
    if (r.ok) remaining.textContent = String((await r.json()).remaining);
  };
  void refresh().catch(() => { remaining.textContent = 'No disponible'; });
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    message.textContent = '';
    clearDisplay();
    button.disabled = true;
    try {
      const response = await fetch('/api/auth/recovery-codes', {
        method: 'POST',
        credentials: 'same-origin',
        headers: getCsrfHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ current_password: byId('recovery-confirm-password').value }),
      });
      if (!response.ok) {
        message.textContent = response.status === 400
          ? 'La contraseña actual es incorrecta.'
          : 'No se han podido generar códigos de recuperación.';
        return;
      }
      const data = await response.json();
      output.textContent = data.codes.join('\n');
      generated.classList.remove('hidden');
      form.reset();
      message.textContent = 'Nuevos códigos generados. Los anteriores han quedado invalidados.';
      remaining.textContent = String(data.count);
    } catch (_) {
      message.textContent = 'Error de conexión.';
    } finally {
      button.disabled = false;
    }
  });
  byId('recovery-copy-button').addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(output.textContent);
      message.textContent = 'Códigos copiados. Guárdalos en un lugar privado.';
    } catch (_) { message.textContent = 'Selecciona y copia manualmente los códigos.'; }
  });
  byId('recovery-hide-button').addEventListener('click', clearDisplay);
  window.addEventListener('pagehide', clearDisplay);
}

async function bootstrap() {
  const user = await checkAuth();
  if (!user) {
    return;
  }

  await fetchCsrfToken();


  attachNavigation();
  attachSettingsForm();
  attachPasswordChange();
  attachRecoveryCodes();
  attachTelegramTestButton();
  attachDatabaseReset();
  attachTradeDiagnosticsToggle();
  document.addEventListener('click', () => {
    hideHourlyVolumeTooltip();
    hidePnlTooltip();
  });
  setTelegramButtonBusy(false);

  try {
    await loadSettings();
    setSettingsFeedback('');
  } catch (error) {
    setSettingsFeedback('No fue posible cargar ajustes.', 'error');
    console.error(error);
  }

  try {
    await loadAutomationStatus();
  } catch (error) {
    setAutomationStatusBadge(false);
    setAutomationField('automation-interval', '—');
    setAutomationField('automation-last-cycle', '—');
    setAutomationField('automation-next-cycle', '—');
    setAutomationStaleWarning(false);
    console.error(error);
  }

  try {
    await loadTelegramStatus();
    setTelegramFeedback('');
  } catch (error) {
    setTelegramFeedback('No fue posible cargar estado de Telegram.', 'error');
    console.error(error);
  }

  await refreshDashboard();
  void loadPnlChart();

  const hashView = window.location.hash ? window.location.hash.replace('#', '') : '';
  if (['home', 'history', 'settings'].includes(hashView)) {
    setActiveView(hashView);
  } else if (hashView === 'settings-modal') {
    setActiveView('settings');
    const modal = byId('reset-confirm-modal');
    if (modal) {
      modal.classList.remove('hidden');
    }
  }
}

bootstrap();

