// 서비스 화면(app.html). 해시 경로로 나눈 단일 페이지.
const $ = (s, r = document) => r.querySelector(s), $$ = (s, r = document) => [...r.querySelectorAll(s)];
const view = $('#view'), navEl = $('#appnav');
let ME = null, LANGS = {}, PROVIDERS = [], ALERTS = 0, SAFETY = false;
const h = (tag, attrs = {}, ...kids) => {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
    else if (k === 'class') e.className = v;
    else if (k === 'value') e.value = v;
    else if (v === true) e.setAttribute(k, '');
    else if (v !== false && v != null) e.setAttribute(k, v);
  }
  kids.flat(Infinity).forEach(c => c != null && e.append(c.nodeType ? c : document.createTextNode(c)));
  return e;
};
const API = async (path, method = 'GET', body) => {
  const r = await fetch('api/' + path, { method, credentials: 'same-origin', headers: body !== undefined ? { 'Content-Type': 'application/json' } : {}, body: body !== undefined ? JSON.stringify(body) : undefined });
  const j = await r.json().catch(() => ({}));
  if (r.status === 401) { location.href = 'login.html'; throw new Error('로그인이 필요합니다.'); }
  if (j.must_change) { location.hash = '#/password'; }
  if (!r.ok) throw new Error(j.error || '처리하지 못했습니다.');
  return j;
};
const toast = (m, bad) => { const t = h('div', { class: 'toast' + (bad ? ' bad' : ''), role: 'status' }, m); document.body.append(t); setTimeout(() => t.remove(), 3500); };
const act = fn => async e => { e?.preventDefault?.(); try { await fn(e); } catch (x) { toast(x.message, true); } };
const fmt = t => { t = Math.max(0, +t || 0); return Math.floor(t / 60) + ':' + String(Math.floor(t % 60)).padStart(2, '0'); };
const isMgr = () => ME.role !== 'worker', isAdmin = () => ME.role === 'admin';
const page = (title, ...kids) => { view.replaceChildren(...h('div', {}, h('h1', {}, title), kids).childNodes); document.title = title; };
const put = (el, ...kids) => el.replaceChildren(...h('div', {}, kids).childNodes);
const field = (label, el) => h('label', { class: 'af' }, h('span', {}, label), el);
const input = (a = {}) => h('input', a);
const sel = (opts, value, a = {}) => { const s = h('select', a, opts.map(([v, t]) => h('option', { value: v }, t))); if (value != null) s.value = value; return s; };
const table = (heads, rows) => h('div', { class: 'tbl' }, h('table', {}, h('thead', {}, h('tr', {}, heads.map(t => h('th', {}, t)))), h('tbody', {}, rows.map(r => h('tr', {}, r.map(c => h('td', {}, c)))))));
const empty = t => h('p', { class: 'muted' }, t);
const badge = (t, cls = '') => h('span', { class: 'bdg ' + cls }, t);
const ST = { done: ['이수', 'ok'], outdated: ['재이수 필요', 'warn'], doing: ['진행 중', 'info'], todo: ['미이수', 'bad'] };
const stBadge = s => badge(...(ST[s] || [s]));
const dl = (href, t) => h('a', { class: 'btn ghost', href }, t);

// ---------- 도형·강조 표시 ----------
const svgEl = (t, a = {}) => { const e = document.createElementNS('http://www.w3.org/2000/svg', t); Object.entries(a).forEach(([k, v]) => e.setAttribute(k, v)); return e; };
const drawAnn = (svg, rows) => {
  svg.replaceChildren(svgEl('defs'));
  svg.firstChild.innerHTML = '<marker id="ah" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="context-stroke"/></marker>';
  rows.forEach(a => {
    const X = a.x * 1000, Y = a.y * 1000, W = a.w * 1000, H = a.h * 1000, st = { stroke: a.color, 'stroke-width': 8, fill: 'none', 'vector-effect': 'non-scaling-stroke' };
    if (a.kind === 'circle') svg.append(svgEl('ellipse', { cx: X + W / 2, cy: Y + H / 2, rx: Math.abs(W / 2), ry: Math.abs(H / 2), ...st, 'stroke-width': 4 }));
    if (a.kind === 'rect') svg.append(svgEl('rect', { x: Math.min(X, X + W), y: Math.min(Y, Y + H), width: Math.abs(W), height: Math.abs(H), ...st, 'stroke-width': 4 }));
    if (a.kind === 'arrow') svg.append(svgEl('line', { x1: X, y1: Y, x2: X + W, y2: Y + H, ...st, 'stroke-width': 5, 'marker-end': 'url(#ah)' }));
    if (a.kind === 'text') { const t = svgEl('text', { x: X, y: Y, fill: a.color, 'font-size': 48, 'font-weight': 700, stroke: '#fff', 'stroke-width': 2, 'paint-order': 'stroke' }); t.textContent = a.text; svg.append(t); }
  });
};

const annEditor = (m, v) => {
  const video = h('video', { controls: true, src: `api/versions/${v.id}/video`, preload: 'metadata' });
  const svg = svgEl('svg', { class: 'ann edit', viewBox: '0 0 1000 1000', preserveAspectRatio: 'none' });
  const kind = sel([['circle', '원'], ['rect', '사각형'], ['arrow', '화살표'], ['text', '글자']], 'circle', { class: 'js-ann-kind' });
  const color = input({ type: 'color', value: '#e8531b' }), len = input({ type: 'number', value: 3, min: 0.5, step: 0.5, class: 'n', 'aria-label': '표시 시간(초)' }), word = input({ placeholder: '글자 (글자 도형일 때)' });
  let rows = [], start = null;
  const list = h('div', {});
  const redraw = () => {
    drawAnn(svg, rows.filter(a => video.currentTime >= a.start && video.currentTime < a.end));
    list.replaceChildren(...rows.map((a, i) => h('div', { class: 'row' }, `${fmt(a.start)}~${fmt(a.end)} ${{ circle: '원', rect: '사각형', arrow: '화살표', text: '글자 ' + a.text }[a.kind]}`,
      h('button', { class: 'btn ghost', onclick: () => { video.currentTime = a.start; } }, '보기'), h('button', { class: 'btn ghost', onclick: () => { rows.splice(i, 1); redraw(); } }, '삭제'))));
  };
  const pt = e => { const r = svg.getBoundingClientRect(); return [(e.clientX - r.left) / r.width, (e.clientY - r.top) / r.height]; };
  svg.addEventListener('pointerdown', e => { video.pause(); start = pt(e); svg.setPointerCapture(e.pointerId); });
  svg.addEventListener('pointerup', e => {
    if (!start) return; const [x2, y2] = pt(e), [x, y] = start; start = null;
    if (kind.value === 'text' && !word.value.trim()) return toast('글자를 입력하세요.', true);
    const t = video.currentTime;
    rows.push({ start: +t.toFixed(2), end: +Math.min(v.duration, t + (+len.value || 3)).toFixed(2), kind: kind.value, x, y, w: x2 - x || 0.1, h: y2 - y || 0.1, color: color.value, text: word.value });
    redraw();
  });
  video.addEventListener('timeupdate', redraw); video.addEventListener('seeked', redraw);
  API(`versions/${v.id}/annotations`).then(r => { rows = r.rows; redraw(); });
  return h('section', { class: 'panel' }, h('h2', {}, '도형·강조 표시'), h('p', { class: 'muted' }, '영상을 멈춘 시점에서 화면을 끌어 원·사각형·화살표·글자를 그립니다. 정한 시간만큼 학습 화면에 겹쳐 보입니다.'),
    h('div', { class: 'row' }, kind, color, len, '초 동안', word), h('div', { class: 'vwrap' }, video, svg), list,
    h('button', { class: 'btn js-save-ann', onclick: act(async () => { await API(`versions/${v.id}/annotations`, 'PUT', { rows }); toast('표시를 저장했습니다.'); }) }, '표시 저장'));
};

// 설명 음성 녹음: 영상을 소리 없이 틀어 두고 마이크로 설명을 녹음해 영상 소리를 바꾼다. 녹음에서 자막을 자동으로 만든다
const voiceBox = (m, v) => {
  const video = h('video', { src: `api/versions/${v.id}/video`, muted: true, playsinline: true, class: 'small' });
  let rec = null, chunks = [];
  const st = h('p', { class: 'muted' });
  const go = h('button', { class: 'btn ghost js-vo', onclick: act(async () => {
    const mic = await navigator.mediaDevices.getUserMedia({ audio: true });
    rec = new MediaRecorder(mic); chunks = [];
    rec.ondataavailable = e => e.data.size && chunks.push(e.data);
    rec.onstop = async () => {
      mic.getTracks().forEach(t => t.stop()); st.textContent = '올리는 중…';
      try {
        const r = await fetch(`api/versions/${v.id}/voiceover`, { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/octet-stream' }, body: new Blob(chunks, { type: rec.mimeType }) });
        const j = await r.json(); if (!r.ok) throw new Error(j.error);
        toast(j.asr ? '새 버전을 만들었고 자막을 만드는 중입니다.' : '새 버전을 만들었습니다.'); R.edit(m.id);
      } catch (e) { toast(e.message, true); st.textContent = ''; }
    };
    video.currentTime = 0; await video.play(); rec.start(1000); st.textContent = '녹음 중… 영상이 끝나면 자동으로 멈춥니다.';
    video.onended = () => rec.state === 'recording' && rec.stop();
  }) }, '설명 음성 녹음 시작');
  return h('section', { class: 'panel' }, h('h2', {}, '설명 음성 덮어쓰기'), h('p', { class: 'muted' }, '영상을 보면서 설명을 말하면 영상 소리를 녹음으로 바꾼 새 버전이 만들어지고, 녹음에서 자막이 자동으로 생깁니다.'),
    video, h('p', { class: 'row' }, go, h('button', { class: 'btn ghost', onclick: () => { video.pause(); rec?.state === 'recording' && rec.stop(); } }, '녹음 끝내기')), st);
};

// ---------- 내 교육 ----------
const R = {};
const noticeBar = rows => rows.length ? h('div', { class: 'notice' }, h('b', {}, `기한 알림 ${rows.length}건`), h('ul', {}, rows.map(r => h('li', {},
  h('a', { href: r.kind === 'edu' ? '#/play/' + r.id : '#/tasks' }, (r.kind === 'edu' ? '교육: ' : '과제: ') + r.title), ` · 기한 ${r.due} `, badge(r.left < 0 ? `${-r.left}일 지남` : r.left === 0 ? '오늘까지' : `${r.left}일 남음`, r.left < 0 ? 'bad' : 'warn'))))) : null;

R.my = async () => {
  const [{ assigned, history }, { courses }, nt] = await Promise.all([API('my'), API('courses'), API('notices')]);
  const mine = courses.filter(c => c.items.length);
  page('내 교육', noticeBar(nt.rows),
    assigned.length ? h('ul', { class: 'cards' }, assigned.map(m => h('li', { class: 'mc' }, h('a', { href: '#/play/' + m.id },
      m.current_version ? h('img', { src: `api/versions/${m.current_version}/thumb`, alt: '', loading: 'lazy' }) : null,
      h('b', {}, m.title), h('span', {}, stBadge(m.st), m.due ? ' 기한 ' + m.due : '', ` 시청 ${Math.round(m.pct)}%`))))) : empty('배정된 교육이 없습니다.'),
    mine.length ? [h('h2', {}, '교육 과정'), table(['과정', '구성', '이수'], mine.map(c => [c.title, c.items.map(i => i.title).join(', '), `${c.items.filter(i => i.st === 'done').length}/${c.items.length}`]))] : [],
    h('h2', {}, '이수 기록'),
    history.length ? table(['시각', '교육', '버전', '점수', '언어'], history.map(r => [r.created, r.title, 'v' + r.no, r.score, LANGS[r.lang] || r.lang])) : empty('아직 없습니다.'));
};

R.play = async id => {
  const m = await API('manuals/' + id);
  const v = m.version;
  if (v && m.step_langs?.includes(ME.lang)) { try { m.steps = (await API(`versions/${v.id}/steps?lang=${ME.lang}`)).steps; } catch {} }
  if (m.title_tr) m.title = m.title_tr;
  if (!v || v.state !== 'ready') return page(m.title, empty('처리하는 중입니다.'));
  const doc = !v.file;
  const star = h('button', { class: 'btn ghost js-star', onclick: act(async () => { m.bookmarked = !m.bookmarked; await API(`manuals/${id}/bookmark`, 'POST', { on: m.bookmarked }); star.textContent = m.bookmarked ? '★ 즐겨찾기됨' : '☆ 즐겨찾기'; }) }, m.bookmarked ? '★ 즐겨찾기됨' : '☆ 즐겨찾기');
  let sent = m.my_pct, curLang = ME.lang in LANGS ? ME.lang : 'ko';
  const box = h('div', { class: 'panel' });
  const report = pct => { if (pct - sent >= 5 || (pct >= 99 && sent < 99)) { sent = pct; API(`versions/${v.id}/progress`, 'POST', { pct, lang: curLang }).then(refresh).catch(() => {}); } };
  let main, side = null, langSel = null, extra = [];
  if (doc) {
    // 문서 매뉴얼: 단계를 끝까지 넘기면 열람 완료
    let at = 0;
    const card = h('div', { class: 'docstep' }), pos = h('span', { class: 'muted' });
    const show = () => {
      const s = m.steps[at] || { title: '내용이 없습니다.' };
      put(card, h('h2', {}, `${at + 1}. ${s.title}`), s.image ? h('img', { src: `api/images/${s.image}`, alt: s.title }) : null,
        s.warn ? h('p', { class: 'warn' }, '주의: ' + s.warn) : null, s.note ? h('p', { class: 'note' }, s.note) : null);
      pos.textContent = ` ${at + 1} / ${m.steps.length}`;
      report(100 * (at + 1) / Math.max(1, m.steps.length));
    };
    main = h('div', {}, card, h('p', { class: 'row' }, h('button', { class: 'btn ghost', onclick: () => { if (at > 0) { at--; show(); } } }, '이전'),
      h('button', { class: 'btn js-next', onclick: () => { if (at < m.steps.length - 1) { at++; show(); } } }, '다음'), pos,
      h('button', { class: 'btn ghost js-offline', onclick: act(async e => {
        if (!('caches' in window)) throw new Error('이 브라우저는 오프라인 저장을 지원하지 않습니다.');
        const c = await caches.open('safeclip-offline');
        for (const u of ['api/me', `api/manuals/${id}`, ...m.step_langs.map(l => `api/versions/${v.id}/steps?lang=${l}`), ...m.steps.filter(s => s.image).map(s => `api/images/${s.image}`)]) { const r = await fetch(u, { credentials: 'same-origin' }); if (r.ok) await c.put(u, r); }
        e.target.disabled = true; e.target.textContent = '오프라인 저장됨'; toast('인터넷 없이도 이 문서를 볼 수 있습니다.');
      }) }, '오프라인 저장')));
    setTimeout(show);
  } else {
    const video = h('video', { controls: true, playsinline: true, preload: 'metadata', src: `api/versions/${v.id}/video` });
    const langs = m.sub_langs;
    curLang = langs.includes(ME.lang) ? ME.lang : (langs[0] || 'ko');
    langs.forEach(l => video.append(h('track', { kind: 'subtitles', srclang: l, label: LANGS[l] || l, src: `api/versions/${v.id}/subs.vtt?lang=${l}`, default: l === curLang })));
    // AI 읽기 음성: 켜면 영상 소리를 끄고 같은 시점에 맞춰 재생
    const voice = h('audio', { preload: 'none' }); let useVoice = false;
    const sync = () => { if (!useVoice) return; if (Math.abs(voice.currentTime - video.currentTime) > 0.3) voice.currentTime = video.currentTime; video.paused ? voice.pause() : voice.play().catch(() => {}); };
    ['play', 'pause', 'seeked', 'ratechange'].forEach(ev => video.addEventListener(ev, () => { voice.playbackRate = video.playbackRate; sync(); }));
    const speed = sel([['0.5', '0.5배'], ['0.75', '0.75배'], ['1', '보통 속도'], ['1.25', '1.25배'], ['1.5', '1.5배'], ['2', '2배']], '1', { class: 'js-speed', 'aria-label': '재생 속도', onchange: e => { video.playbackRate = +e.target.value; } });
    const voiceSel = m.narrations.length ? sel([['', '원래 소리'], ...m.narrations.map(l => [l, 'AI 음성 ' + (LANGS[l] || l)])], '', { class: 'js-voice', onchange: e => {
      useVoice = !!e.target.value; video.muted = useVoice; voice.pause();
      if (useVoice) { voice.src = `api/versions/${v.id}/narration?lang=${e.target.value}`; sync(); }
    } }) : null;
    const seen = new Set(); let last = -1;
    video.addEventListener('timeupdate', () => {
      const s = Math.floor(video.currentTime);
      if (!video.seeking && !video.paused && (s === last || s === last + 1)) seen.add(s);
      last = s;
      report(Math.min(100, 100 * seen.size / Math.max(1, Math.floor(video.duration || v.duration))));
      $$('.step').forEach(el => el.classList.toggle('on', video.currentTime >= +el.dataset.s && video.currentTime < +el.dataset.e));
      if (useVoice && Math.abs(voice.currentTime - video.currentTime) > 0.5) voice.currentTime = video.currentTime;
    });
    side = h('ol', { class: 'steps' }, m.steps.map(s => h('li', { class: 'step', 'data-s': s.start, 'data-e': s.end },
      h('button', { onclick: () => { video.currentTime = s.start; video.play().catch(() => {}); } }, h('b', {}, `${fmt(s.start)} ${s.title}`)),
      s.warn ? h('p', { class: 'warn' }, '주의: ' + s.warn) : null, s.note ? h('p', {}, s.note) : null)));
    langSel = langs.length ? sel(langs.map(l => [l, LANGS[l] || l]), curLang, { onchange: e => { curLang = e.target.value; [...video.textTracks].forEach(t => (t.mode = t.language === curLang ? 'showing' : 'disabled')); } }) : null;
    const overlay = svgEl('svg', { class: 'ann', viewBox: '0 0 1000 1000', preserveAspectRatio: 'none' });
    API(`versions/${v.id}/annotations`).then(({ rows }) => video.addEventListener('timeupdate', () => drawAnn(overlay, rows.filter(a => video.currentTime >= a.start && video.currentTime < a.end)))).catch(() => {});
    main = h('div', { class: 'vwrap' }, video, overlay);
    let cached = false;
    video.addEventListener('play', () => { if (!cached && 'caches' in window && navigator.serviceWorker?.controller) { cached = true; saveOff(true).catch(() => {}); } });
    const saveOff = async quiet => {
      if (!quiet) { offline.disabled = true; offline.textContent = '저장 중…'; }
      const c = await caches.open('safeclip-offline');
      const urls = ['api/me', `api/manuals/${id}`, `api/versions/${v.id}/video`, `api/versions/${v.id}/thumb`, `api/versions/${v.id}/annotations`, ...m.step_langs.map(l => `api/versions/${v.id}/steps?lang=${l}`), ...langs.map(l => `api/versions/${v.id}/subs.vtt?lang=${l}`), ...m.narrations.map(l => `api/versions/${v.id}/narration?lang=${l}`)];
      for (const u of urls) { const r = await fetch(u, { credentials: 'same-origin' }); if (r.ok) await c.put(u, r); }
      offline.disabled = true; offline.textContent = '오프라인 저장됨'; if (!quiet) toast('인터넷 없이도 이 교육을 볼 수 있습니다.');
    };
    const offline = h('button', { class: 'btn ghost js-offline', onclick: act(async () => {
      if (!('caches' in window) || !navigator.serviceWorker) throw new Error('이 브라우저는 오프라인 저장을 지원하지 않습니다.');
      await saveOff(false);
    }) }, '오프라인 저장');
    extra = [' ', speed, voiceSel ? [' · ', voiceSel] : null, ' ', offline, voice];
  }
  const refresh = () => {
    box.replaceChildren();
    if (m.my_done) return box.append(h('p', { class: 'okmsg' }, '이수 완료된 교육입니다.'));
    const pct = Math.max(sent, m.my_pct);
    box.append(h('p', {}, doc ? `열람 ${Math.round(pct)}% (마지막 단계까지 보면 확인 절차가 열립니다)` : `시청률 ${Math.round(pct)}% (90% 이상이면 확인 절차가 열립니다)`));
    if (pct < 90) return;
    const answers = {};
    m.quiz.forEach((z, i) => box.append(h('fieldset', { class: 'qz' }, h('legend', {}, `${i + 1}. ${z.step_ord != null && m.steps[z.step_ord] ? '[' + (z.step_ord + 1) + '단계] ' : ''}${z.question}`),
      z.options.map((o, j) => h('label', {}, input({ type: 'radio', name: 'q' + z.id, onchange: () => (answers[z.id] = j) }), ' ' + o)))));
    const c = h('canvas', { width: 320, height: 120, class: 'sign', 'aria-label': '서명' }); const g = c.getContext('2d'); let on = false, drew = false;
    g.lineWidth = 2; g.lineCap = 'round';
    const pos = e => { const r = c.getBoundingClientRect(); return [(e.clientX - r.left) * c.width / r.width, (e.clientY - r.top) * c.height / r.height]; };
    c.addEventListener('pointerdown', e => { on = true; c.setPointerCapture(e.pointerId); g.beginPath(); g.moveTo(...pos(e)); });
    c.addEventListener('pointermove', e => { if (on) { g.lineTo(...pos(e)); g.stroke(); drew = true; } });
    c.addEventListener('pointerup', () => (on = false));
    box.append(h('p', {}, '서명'), c, h('p', {}, h('button', { class: 'btn ghost', onclick: () => { g.clearRect(0, 0, c.width, c.height); drew = false; } }, '지우기'), ' ',
      h('button', { class: 'btn js-complete', onclick: act(async () => {
        if (!drew) throw new Error('서명을 입력하세요.');
        const r = await API(`manuals/${id}/complete`, 'POST', { answers, signature: c.toDataURL('image/png') });
        const weak = Object.entries(r.steps || {}).filter(([k, s]) => k !== 'all' && s < 100).map(([k]) => +k + 1);
        if (!r.passed) return toast(`${r.score}점입니다. ${r.need}점 이상이어야 합니다.${weak.length ? ' 다시 볼 단계: ' + weak.join(', ') : ''} 다시 풀어 주세요.`, true);
        toast('이수 처리되었습니다.'); m.my_done = true; refresh();
      }) }, '이수 확인')));
  };
  page(m.title, h('p', { class: 'muted' }, `${doc ? '문서' : '영상'} 매뉴얼 v${v.no} · 담당 ${m.owner || '-'}`, langSel ? [' · 자막 ', langSel] : null, ' ', star, extra),
    h('div', { class: doc ? '' : 'player' }, main, side && side.children.length ? side : null), box);
  refresh();
};

// ---------- 매뉴얼 관리 ----------
R.manuals = async () => {
  const [{ manuals }, { rows: folders }] = await Promise.all([API('manuals'), API('folders')]);
  const under = id => { const ids = new Set([id]); let grow = true; while (grow) { grow = false; folders.forEach(f => { if (ids.has(f.parent_id) && !ids.has(f.id)) { ids.add(f.id); grow = true; } }); } return ids; };
  const fpath = f => { const out = []; let x = f; while (x) { out.unshift(x.name); x = folders.find(y => y.id === x.parent_id); } return out.join(' › '); };
  const fSel = sel([['', '모든 폴더'], ...folders.map(f => [f.id, fpath(f)])], '', { class: 'js-folder-filter' });
  const t = input({ placeholder: '매뉴얼 제목' }), cat = input({ placeholder: '분류 (예: 안전)' }), dept = input({ placeholder: '부서' }), kind = sel([['video', '영상 매뉴얼'], ['doc', '문서 매뉴얼']], 'video');
  const qbox = input({ type: 'search', placeholder: '제목·분류·태그 검색', class: 'grow js-search' }), onlyStar = input({ type: 'checkbox', class: 'js-only-star' });
  const tags = [...new Set(manuals.flatMap(m => (m.tags || '').split(',').map(x => x.trim()).filter(Boolean)))];
  const tagSel = sel([['', '모든 태그'], ...tags.map(x => [x, '#' + x])], '');
  const list = h('ul', { class: 'cards' });
  const draw = () => {
    const k = qbox.value.trim().toLowerCase();
    const rows = manuals.filter(m => (!k || `${m.title} ${m.category} ${m.tags}`.toLowerCase().includes(k)) && (!onlyStar.checked || m.bookmarked) && (!tagSel.value || (m.tags || '').split(',').map(x => x.trim()).includes(tagSel.value)) && (!fSel.value || under(+fSel.value).has(m.folder_id)));
    list.replaceChildren(...rows.map(m => h('li', { class: 'mc' }, h('a', { href: (isMgr() ? '#/edit/' : '#/play/') + m.id },
      m.current_version && m.kind !== 'doc' ? h('img', { src: `api/versions/${m.current_version}/thumb`, alt: '', loading: 'lazy' }) : h('div', { class: 'docthumb' }, '문서'),
      h('b', {}, (m.bookmarked ? '★ ' : '') + m.title),
      h('span', {}, badge({ published: '공개', review: '승인 중', draft: '초안' }[m.status] || m.status, m.status === 'published' ? 'ok' : m.status === 'review' ? 'info' : ''), ' ', m.category, m.version ? ` v${m.version.no}` : '', (m.tags || '').split(',').filter(x => x.trim()).map(x => ' #' + x.trim()).join(''))))));
    if (!rows.length) list.replaceChildren(empty('조건에 맞는 매뉴얼이 없습니다.'));
  };
  qbox.oninput = onlyStar.onchange = tagSel.onchange = fSel.onchange = draw; draw();
  const pdf = input({ type: 'file', accept: '.pdf,.docx,.txt', class: 'js-pdf-manual' });
  const pdfBtn = h('button', { type: 'button', class: 'btn ghost js-pdf-manual-go', onclick: act(async () => {
    if (!pdf.files[0]) throw new Error('작업표준서 파일을 고르세요.');
    const j = await busy(pdfBtn, 'AI가 읽는 중…', () => postFile('ai/manual', pdf.files[0], { 'X-Name': encodeURIComponent(pdf.files[0].name.replace(/\.[^.]+$/, '')) }));
    toast(`${j.steps}단계 문서 매뉴얼 초안을 만들었습니다.`); location.hash = '#/edit/' + j.id;
  }) }, 'PDF로 새 문서 매뉴얼');
  page('매뉴얼',
    isMgr() ? h('form', { class: 'row', onsubmit: act(async () => { const r = await API('manuals', 'POST', { title: t.value, category: cat.value, dept: dept.value, kind: kind.value }); location.hash = '#/edit/' + r.id; }) }, kind, t, cat, dept, h('button', { class: 'btn' }, '새 매뉴얼')) : null,
    isMgr() ? h('div', { class: 'row' }, pdf, pdfBtn, h('a', { href: '#/folders', class: 'btn ghost' }, '폴더 관리')) : null,
    h('div', { class: 'row' }, qbox, fSel, tagSel, h('label', {}, onlyStar, ' 즐겨찾기만')), list);
};

const upload = (id, file, reason, bar, auto) => new Promise((ok, no) => {
  const r = new XMLHttpRequest(); r.open('POST', `api/manuals/${id}/versions`);
  r.setRequestHeader('Content-Type', 'application/octet-stream'); r.setRequestHeader('X-Reason', encodeURIComponent(reason)); if (auto) r.setRequestHeader('X-Auto', '1');
  r.upload.onprogress = e => { bar.value = e.loaded / e.total; };
  r.onload = () => { let j = {}; try { j = JSON.parse(r.responseText); } catch {} r.status === 200 ? ok(j) : no(new Error(j.error || '올리지 못했습니다.')); };
  r.onerror = () => no(new Error('전송이 끊겼습니다.')); r.send(file);
});

R.edit = async id => {
  const [m, { users }, { rows: folders }] = await Promise.all([API('manuals/' + id), API('users'), API('folders')]);
  const v = m.version, doc = m.kind === 'doc';
  const title = input({ value: m.title }), cat = input({ value: m.category }), dept = input({ value: m.dept }), tags = input({ value: m.tags || '', placeholder: '쉼표로 구분 (예: 프레스, 신입)' });
  const scope = input({ value: m.scope || '', placeholder: '비우면 전체 공개, 부서명을 쉼표로 적으면 그 부서와 배정자만' });
  const owner = sel([['', '담당자 없음'], ...users.map(u => [u.id, u.name])], m.owner_id || '');
  const stat = sel([['draft', '초안'], ['review', '승인 중'], ['published', '공개'], ['archived', '보관(목록에서 숨김)']], m.status);
  const info = h('form', { class: 'panel', onsubmit: act(async () => { await API('manuals/' + id, 'PUT', { title: title.value, category: cat.value, dept: dept.value, tags: tags.value, scope: scope.value, status: stat.value, owner_id: owner.value ? +owner.value : null }); toast('저장했습니다.'); R.edit(id); }) },
    field('제목', title), field('분류', cat), field('부서', dept), field('태그', tags), field('공개 범위', scope), field('담당자', owner), field('상태', stat), h('button', { class: 'btn' }, '저장'), folderPick(m, folders));
  const versions = m.versions.length ? table(['버전', '사유', '작성', '상태', '시각', ''], m.versions.map(x => ['v' + x.no, x.reason, x.author, x.state === 'ready' ? '완료' : x.state === 'failed' ? '실패: ' + x.error : '처리 중', x.created,
    x.state === 'ready' && x.file ? h('span', {}, h('a', { href: `api/versions/${x.id}/video`, target: '_blank' }, '보기'), ' · ', h('a', { href: `api/versions/${x.id}/download` }, '내려받기')) : ''])) : null;
  let up;
  if (doc) {
    const reason = input({ placeholder: '개정 사유', class: 'grow' });
    up = h('section', { class: 'panel' }, h('h2', {}, '버전'), h('form', { class: 'row', onsubmit: act(async () => { await API(`manuals/${id}/docversion`, 'POST', { reason: reason.value }); toast('새 버전을 만들었습니다. 단계를 고치고 저장하세요.'); R.edit(id); }) }, reason, h('button', { class: 'btn ghost' }, '개정판 만들기')), versions);
  } else {
    const file = input({ type: 'file', accept: 'video/*', class: 'js-file' }), reason = input({ placeholder: m.versions.length ? '개정 사유 (필수)' : '최초 등록' }), bar = h('progress', { max: 1, value: 0 });
    const auto = input({ type: 'checkbox', class: 'js-auto', checked: true });
    const send = async blob => { const r = await upload(id, blob, reason.value, bar, auto.checked); toast(auto.checked ? '변환을 시작했습니다. 끝나면 자막과 단계를 자동으로 만듭니다.' : '변환을 시작했습니다.'); await waitV(r.version_id); R.edit(id); };
    // 브라우저에서 바로 촬영·화면 녹화
    const live = h('video', { muted: true, playsinline: true, class: 'small', hidden: true });
    let rec = null, chunks = [];
    const startRec = screen => act(async () => {
      let stream = screen ? await navigator.mediaDevices.getDisplayMedia({ video: { cursor: 'always' }, audio: true }) : await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' }, audio: true });
      const extraTracks = [];
      if (screen) {  // 화면 녹화: 마우스 움직임과 함께 마이크 설명 음성을 화면 소리와 섞어 녹음
        const mic = await navigator.mediaDevices.getUserMedia({ audio: true }).catch(() => null);
        if (mic) {
          const ac = new AudioContext(), dest = ac.createMediaStreamDestination();
          [stream, mic].forEach(s => s.getAudioTracks().length && ac.createMediaStreamSource(s).connect(dest));
          extraTracks.push(...mic.getTracks());
          stream = new MediaStream([...stream.getVideoTracks(), ...dest.stream.getAudioTracks(), ...[]]); stream._src = [mic];
        }
      }
      live.srcObject = stream; live.hidden = false; live.play(); chunks = [];
      rec = new MediaRecorder(stream); rec.ondataavailable = e => e.data.size && chunks.push(e.data);
      rec.onstop = () => { stream.getTracks().forEach(t => t.stop()); extraTracks.forEach(t => t.stop()); live.srcObject?.getTracks?.().forEach(t => t.stop()); live.hidden = true; send(new Blob(chunks, { type: rec.mimeType || 'video/webm' })).catch(e => toast(e.message, true)); };
      rec.start(1000); stopBtn.disabled = false;
    });
    const stopBtn = h('button', { type: 'button', class: 'btn', disabled: true, onclick: () => { rec?.stop(); stopBtn.disabled = true; } }, '녹화 끝내고 올리기');
    up = h('form', { class: 'panel', onsubmit: act(async () => { if (!file.files[0]) throw new Error('영상을 선택하세요.'); await send(file.files[0]); }) },
      h('h2', {}, '영상 올리기'), field('파일', file), field('개정 사유', reason), h('label', {}, auto, ' 올린 뒤 AI 자막·단계 나누기까지 자동으로'), bar, h('p', {}, h('button', { class: 'btn' }, '올리기')),
      h('p', { class: 'row' }, h('button', { type: 'button', class: 'btn ghost', onclick: startRec(false) }, '카메라로 촬영'), h('button', { type: 'button', class: 'btn ghost', onclick: startRec(true) }, '화면 녹화'), stopBtn), live, versions);
  }
  const kids = [info, up];
  if (v && v.state === 'ready') {
    kids.push(stepsEditor(m, v), stepsTransBox(m, v));
    if (!doc) kids.push(annEditor(m, v), subsEditor(m, v), ttsBox(m, v), voiceBox(m, v), exportBox(m, v));
    kids.push(quizEditor(m), approvalBox(m, users), assignBox(m, users), reportBox(m), revisionBox(v));
  }
  page(m.title, h('p', {}, h('a', { href: '#/play/' + id }, '학습 화면 보기')), kids);
};
const waitV = async id => { for (let i = 0; i < 600; i++) { const s = await API(`versions/${id}/status`); if (s.state === 'ready') return; if (s.state === 'failed') throw new Error('변환 실패: ' + s.error); await new Promise(r => setTimeout(r, 1000)); } };

const stepsEditor = (m, v) => {
  const doc = !v.file;
  const video = doc ? null : h('video', { controls: true, src: `api/versions/${v.id}/video`, preload: 'metadata', class: 'small' });
  const list = h('div', { class: 'js-steps' });
  const row = (s = {}) => {
    const a = input({ type: 'number', step: '0.1', min: 0, value: s.start ?? 0, 'aria-label': '시작', class: 'n' }), b = input({ type: 'number', step: '0.1', min: 0, value: s.end ?? v.duration, 'aria-label': '끝', class: 'n' });
    let image = s.image || '';
    const pic = h('span', { class: 'muted' }, image ? '그림 있음' : '');
    const picIn = input({ type: 'file', accept: 'image/png,image/jpeg,image/webp', class: 'js-pic', onchange: act(async e => {
      const f = e.target.files[0]; if (!f) return;
      const r = await fetch('api/images', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/octet-stream' }, body: f });
      const j = await r.json(); if (!r.ok) throw new Error(j.error); image = j.image; pic.textContent = '그림 올림';
    }) });
    const note = doc ? h('textarea', { rows: 3, placeholder: '설명', 'data-k': 'note' }, s.note || '') : input({ placeholder: '설명', value: s.note || '', 'data-k': 'note' });
    const r = h('div', { class: 'row step-row' },
      doc ? null : [a, h('button', { type: 'button', class: 'btn ghost', onclick: () => (a.value = video.currentTime.toFixed(1)) }, '현재→시작'),
        b, h('button', { type: 'button', class: 'btn ghost', onclick: () => (b.value = video.currentTime.toFixed(1)) }, '현재→끝')],
      input({ placeholder: '단계 제목', value: s.title || '', 'data-k': 'title' }), note, input({ placeholder: '주의사항', value: s.warn || '', 'data-k': 'warn' }),
      doc ? [picIn, pic] : null,
      h('button', { type: 'button', class: 'btn ghost', onclick: () => r.remove() }, '삭제'));
    r._get = () => ({ start: +a.value, end: +b.value, title: $('[data-k=title]', r).value, note: $('[data-k=note]', r).value, warn: $('[data-k=warn]', r).value, image });
    list.append(r);
  };
  m.steps.forEach(row);
  // AI: 절차서(PDF·Word·텍스트)에서 단계 골자 만들기, 자막에서 단계 나누기
  const src = input({ type: 'file', accept: '.pdf,.docx,.txt', class: 'js-outline-file' });
  const fromDoc = h('button', { type: 'button', class: 'btn ghost js-outline', onclick: act(async () => {
    if (!src.files[0]) throw new Error('절차서 파일을 고르세요.');
    fromDoc.disabled = true; fromDoc.textContent = 'AI가 읽는 중…';
    try {
      const r = await fetch('api/ai/outline', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/octet-stream' }, body: src.files[0] });
      const j = await r.json(); if (!r.ok) throw new Error(j.error);
      const d = doc ? 0 : v.duration / j.steps.length;
      j.steps.forEach((s, i) => row({ ...s, start: +(i * d).toFixed(1), end: +((i + 1) * d).toFixed(1) })); toast(`${j.steps.length}개 단계를 만들었습니다. 검토 후 저장하세요.`);
    } finally { fromDoc.disabled = false; fromDoc.textContent = '절차서로 단계 만들기'; }
  }) }, '절차서로 단계 만들기');
  const fromSubs = doc ? null : h('button', { type: 'button', class: 'btn ghost js-autosteps', onclick: act(async () => {
    fromSubs.disabled = true;
    try { const j = await API(`versions/${v.id}/autosteps`, 'POST', {}); list.replaceChildren(); j.steps.forEach(row); toast('자막으로 단계를 나눴습니다. 검토 후 저장하세요.'); } finally { fromSubs.disabled = false; }
  }) }, '자막으로 단계 자동 나누기');
  return h('section', { class: 'panel' }, h('h2', {}, doc ? '문서 단계' : '단계 나누기'), video, h('div', { class: 'row' }, src, fromDoc, fromSubs), list,
    h('p', {}, h('button', { class: 'btn ghost', onclick: () => row(doc ? {} : { start: +video.currentTime.toFixed(1) }) }, '단계 추가'), ' ',
      h('button', { class: 'btn js-save-steps', onclick: act(async () => { await API(`versions/${v.id}/steps`, 'PUT', { steps: [...list.children].map(r => r._get()) }); toast('단계를 저장했습니다.'); }) }, '단계 저장')));
};

const ttsBox = (m, v) => {
  const lang = sel(Object.entries(LANGS), 'ko', { class: 'js-tts-lang' }), st = h('p', { class: 'muted js-tts-state' }, m.narrations.length ? '만든 음성: ' + m.narrations.map(l => LANGS[l]).join(', ') : '');
  const run = replace => act(async () => {
    await API(`versions/${v.id}/tts`, 'POST', { lang: lang.value, replace });
    for (let i = 0; i < 900; i++) {
      const { jobs } = await API(`versions/${v.id}/status`); const j = jobs.find(x => x.lang === 'tts-' + lang.value);
      if (j?.state === 'done') { toast(replace ? '음성을 바꾼 새 버전을 만들었습니다.' : '읽기 음성을 만들었습니다.'); return R.edit(m.id); }
      if (j?.state === 'failed') throw new Error(j.error);
      st.textContent = '음성 만드는 중…'; await new Promise(r => setTimeout(r, 2000));
    }
  });
  return h('section', { class: 'panel' }, h('h2', {}, 'AI 자막 읽기 음성'), h('p', { class: 'muted' }, '확정된 자막을 음성으로 읽습니다(Microsoft 음성 합성 사용). 학습 화면에서 원래 소리 대신 고를 수 있습니다.'),
    h('div', { class: 'row' }, lang, h('button', { class: 'btn ghost js-tts', onclick: run(false) }, '읽기 음성 만들기'), h('button', { class: 'btn ghost js-tts-replace', onclick: run(true) }, '영상 소리를 이 음성으로 교체(새 버전)')), st);
};

const approvalBox = (m, users) => {
  const mgr = users.filter(u => u.active && u.role !== 'worker');
  const pick = h('select', { multiple: true, size: 4, class: 'js-approvers' }, mgr.map(u => h('option', { value: u.id }, u.name)));
  const order = h('p', { class: 'muted' });
  const picked = [];
  pick.onchange = () => { [...pick.options].forEach(o => { const i = picked.indexOf(+o.value); if (o.selected && i < 0) picked.push(+o.value); if (!o.selected && i >= 0) picked.splice(i, 1); }); order.textContent = '승인 순서: ' + picked.map(i => mgr.find(u => u.id === i).name).join(' → '); };
  const ST = { wait: '대기', ok: '승인', reject: '반려', cancel: '취소' };
  return h('section', { class: 'panel' }, h('h2', {}, '승인 요청'), h('p', { class: 'muted' }, '고른 순서대로 승인하고, 모두 승인하면 자동으로 공개됩니다.'), pick, order,
    h('button', { class: 'btn ghost js-req-approval', onclick: act(async () => { await API(`manuals/${m.id}/approval`, 'POST', { approver_ids: picked }); toast('승인을 요청했습니다.'); R.edit(m.id); }) }, '승인 요청'),
    m.approvals.length ? table(['단계', '승인자', '결과', '의견', '시각'], m.approvals.map(a => [a.step + 1, a.name, ST[a.status], a.comment, a.at || ''])) : null);
};

const reportBox = m => {
  const out = h('div', {}, empty('불러오는 중…'));
  API(`manuals/${m.id}/report`).then(r => put(out, h('p', {}, `배정 ${r.total}명 · 이수 ${r.done}명 · 열람 ${r.viewers}명 · 평균 시청률 ${r.avg_pct}%`),
    r.rows.length ? table(['이름', '부서', '기한', '상태', '시청', '점수', '이수 시각'], r.rows.map(x => [x.name, x.dept, x.due, stBadge(x.st), x.pct + '%', x.score ?? '', x.at])) : null)).catch(e => out.replaceChildren(empty(e.message)));
  return h('section', { class: 'panel' }, h('h2', {}, '리포트'), out);
};

const subsEditor = (m, v) => {
  const lang = sel(Object.entries(LANGS), 'ko'), list = h('div', {}), st = h('p', { class: 'muted js-sub-state' });
  const load = async () => {
    const { subs } = await API(`versions/${v.id}/subs?lang=${lang.value}`); list.replaceChildren();
    subs.forEach(s => list.append(subRow(s)));
    st.textContent = subs.length ? (subs.every(s => s.confirmed) ? '확정됨' : '초안 (검수 후 확정하세요)') : '자막 없음';
  };
  const subRow = s => {
    const r = h('div', { class: 'row' }, input({ type: 'number', step: '0.1', value: s.start, class: 'n' }), input({ type: 'number', step: '0.1', value: s.end, class: 'n' }), input({ value: s.text, class: 'grow' }), h('button', { class: 'btn ghost', onclick: () => r.remove() }, '삭제'));
    r._get = () => { const i = $$('input', r); return { start: +i[0].value, end: +i[1].value, text: i[2].value }; };
    return r;
  };
  const save = confirm => act(async () => { await API(`versions/${v.id}/subs`, 'PUT', { lang: lang.value, confirm, subs: [...list.children].map(r => r._get()) }); toast(confirm ? '확정했습니다.' : '저장했습니다.'); load(); });
  const wait = async l => { for (let i = 0; i < 3600; i++) { const { jobs } = await API(`versions/${v.id}/status`); const j = jobs.find(x => x.lang === l); if (j?.state === 'done') return; if (j?.state === 'failed') throw new Error(j.error); st.textContent = '처리 중…'; await new Promise(r => setTimeout(r, 2000)); } };
  lang.addEventListener('change', load); load();
  return h('section', { class: 'panel' }, h('h2', {}, 'AI 자막'), h('div', { class: 'row' }, lang,
    h('button', { class: 'btn ghost js-asr', onclick: act(async () => { await API(`versions/${v.id}/subs/draft`, 'POST', {}); lang.value = 'ko'; await wait('ko'); await load(); toast('초안을 만들었습니다.'); }) }, '음성→자막 초안'),
    h('button', { class: 'btn ghost js-trans', onclick: act(async () => { if (lang.value === 'ko') throw new Error('번역할 언어를 고르세요.'); await API(`versions/${v.id}/subs/translate`, 'POST', { lang: lang.value }); await wait(lang.value); await load(); toast('번역했습니다.'); }) }, '이 언어로 번역'),
    h('button', { class: 'btn ghost', onclick: () => list.append(subRow({ start: 0, end: 1, text: '' })) }, '줄 추가'),
    h('button', { class: 'btn ghost', onclick: save(false) }, '저장'), h('button', { class: 'btn js-sub-ok', onclick: save(true) }, '검수 완료·확정')), st, list);
};

const quizEditor = m => {
  const list = h('div', {});
  const row = (z = { question: '', options: ['', ''], answer: 0, step_ord: null }) => {
    const so = sel([['', '전체'], ...m.steps.map(s => [s.ord, `${s.ord + 1}. ${s.title}`])], z.step_ord ?? '', { 'aria-label': '연결 단계' });
    const qi = input({ placeholder: '문제', value: z.question, class: 'grow' }), o = input({ placeholder: '보기 (쉼표로 구분)', value: z.options.join(', '), class: 'grow' }), a = input({ type: 'number', min: 1, value: z.answer + 1, class: 'n', 'aria-label': '정답 번호' });
    const r = h('div', { class: 'row' }, so, qi, o, a, h('button', { class: 'btn ghost', onclick: () => r.remove() }, '삭제'));
    r._get = () => ({ question: qi.value, options: o.value.split(',').map(x => x.trim()).filter(Boolean), answer: +a.value - 1, step_ord: so.value === '' ? null : +so.value });
    list.append(r);
  };
  m.quiz.forEach(row);
  return h('section', { class: 'panel' }, h('h2', {}, '확인 테스트'), h('p', { class: 'muted' }, '문제마다 단계를 연결하면 학습자가 단계별로 얼마나 이해했는지 따로 채점·기록합니다.'), list, h('p', {}, h('button', { class: 'btn ghost', onclick: () => row() }, '문제 추가'), ' ',
    h('button', { class: 'btn', onclick: act(async () => { await API(`manuals/${m.id}/quiz`, 'PUT', { quiz: [...list.children].map(r => r._get()) }); toast('저장했습니다.'); }) }, '테스트 저장')));
};

const assignBox = (m, users) => {
  const depts = [...new Set(users.map(u => u.dept).filter(Boolean))], sites = [...new Set(users.map(u => u.site).filter(Boolean))];
  const d = sel([['', '부서 선택'], ...depts.map(x => [x, x])]), s = sel([['', '사업장 선택'], ...sites.map(x => [x, x])]);
  const u = h('select', { multiple: true, size: 5, class: 'js-assign-users' }, users.filter(x => x.active).map(x => h('option', { value: x.id }, `${x.name} (${x.dept || '-'})`)));
  const due = input({ type: 'date' });
  return h('section', { class: 'panel' }, h('h2', {}, '교육 배정'), field('개인', u), field('부서 전체', d), field('사업장 전체', s), field('기한', due),
    h('button', { class: 'btn js-assign', onclick: act(async () => { const r = await API(`manuals/${m.id}/assign`, 'POST', { user_ids: [...u.selectedOptions].map(o => +o.value), dept: d.value, site: s.value, due: due.value }); toast(`${r.assigned}명에게 배정했습니다.`); }) }, '배정'));
};

R.courses = async () => {
  const [{ courses }, { manuals }, { users }] = await Promise.all([API('courses'), API('manuals'), API('users')]);
  const t = input({ placeholder: '과정 이름' }), ms = h('select', { multiple: true, size: 6 }, manuals.map(m => h('option', { value: m.id }, m.title)));
  const dep = sel([['', '부서 선택'], ...[...new Set(users.map(u => u.dept).filter(Boolean))].map(x => [x, x])]);
  page('교육 과정', h('form', { class: 'panel', onsubmit: act(async () => { await API('courses', 'POST', { title: t.value, manual_ids: [...ms.selectedOptions].map(o => +o.value) }); R.courses(); }) }, field('이름', t), field('매뉴얼', ms), h('button', { class: 'btn' }, '과정 만들기')),
    field('배정할 부서', dep),
    courses.length ? h('div', { class: 'tree' }, courses.map(c => h('details', { open: true }, h('summary', {}, h('b', {}, c.title), ` (${c.items.length}개) `,
      h('button', { class: 'btn ghost', onclick: act(async e => { e.preventDefault(); const r = await API(`courses/${c.id}/assign`, 'POST', { dept: dep.value }); toast(`${r.assigned}명, 매뉴얼 ${r.manuals}개 배정`); }) }, '부서에 배정')),
      h('ul', {}, c.items.map(i => { const li = h('li', {}, h('a', { href: '#/edit/' + i.id }, i.title), ' ', badge(i.status === 'published' ? '공개' : '초안', i.status === 'published' ? 'ok' : ''));
        const sub = h('ul', { class: 'muted' }); li.append(sub);
        API('manuals/' + i.id).then(d => sub.replaceChildren(...d.steps.map(st => h('li', {}, st.title)))).catch(() => {});
        return li; }))))) : empty('과정이 없습니다.'));
};

// ---------- 역량 ----------
R.skills = async () => {
  const dept = decodeURIComponent(location.hash.split('?d=')[1] || '');
  const [m, { rows }] = await Promise.all([API('matrix' + (dept ? '?dept=' + encodeURIComponent(dept) : '')), API('unfinished')]);
  const heads = ['이름', '부서', ...m.manuals.map(x => x.title)];
  const body = m.users.map(u => [u.name, u.dept, ...m.manuals.map(x => { const c = m.cells[`${u.id}:${x.id}`]; return c ? stBadge(c.st) : '-'; })]);
  body.push(['가능 인원', '', ...m.manuals.map(x => String(m.capable[x.id] || 0))]);
  page('인력 역량', h('p', { class: 'row' }, dl('api/matrix.xlsx', '역량표 엑셀'), dl('api/unfinished.xlsx', '미이수자 엑셀'), dl('api/completions.xlsx', '이수 기록 엑셀')),
    table(heads, body), h('h2', {}, `미이수자 ${rows.length}명`),
    rows.length ? table(['이름', '부서', '교육', '기한', '상태'], rows.map(r => [r.name, r.dept, r.title, r.due + (r.overdue ? ' (경과)' : ''), r.st])) : empty('없습니다.'));
};

R.education = async () => {
  const from = input({ type: 'date' }), to = input({ type: 'date' }), out = h('div', {});
  const load = async () => {
    const qs = `from=${from.value}&to=${to.value}`; const { rows } = await API('completions?' + qs);
    out.replaceChildren(rows.length ? table(['이수 시각', '이름', '부서', '사업장', '교육', '버전', '점수', '언어', '서명'], rows.map(r => [r.created, r.name, r.dept, r.site, r.title, 'v' + r.no, r.score, LANGS[r.lang] || r.lang, h('img', { src: r.signature, alt: '서명', class: 'sig' })])) : empty('기록이 없습니다.'));
  };
  from.onchange = to.onchange = act(load); await load();
  page('교육 기록', h('div', { class: 'row' }, from, to, dl('api/completions.xlsx', '엑셀'), h('button', { class: 'btn ghost', onclick: () => print() }, '인쇄')), out);
};

// ---------- 작업 분석 ----------
R.compare = async () => {
  const q0 = new URLSearchParams(location.hash.split('?')[1] || '');
  const a0 = q0.get('a') || '', b0 = q0.get('b') || '';
  const { versions, notes } = await API(`compare?a=${a0 || 0}&b=${b0 || 0}`);
  const opt = versions.map(v => [v.id, `${v.title} v${v.no}${v.standard_version === v.id ? ' (표준)' : ''}`]);
  const a = sel([['', '기준 영상'], ...opt], a0), b = sel([['', '비교 영상'], ...opt], b0);
  const go = () => { location.hash = `#/compare?a=${a.value}&b=${b.value}`; };
  a.onchange = b.onchange = go;
  const kids = [h('div', { class: 'row' }, a, b)];
  if (a0 && b0) {
    const va = h('video', { src: `api/versions/${a0}/video`, controls: true, class: 'js-va' }), vb = h('video', { src: `api/versions/${b0}/video`, controls: true, class: 'js-vb' });
    const both = f => [va, vb].forEach(f);
    const memo = input({ placeholder: '현재 시점 메모', class: 'grow' });
    const [{ users }, ea, eb] = await Promise.all([API('users'), API(`versions/${a0}/elements`), API(`versions/${b0}/elements`)]);
    const av = versions.find(v => v.id == a0);
    // 요소 작업: 간트 차트, 요소별 동시 재생
    let stopAt = null;
    [va, vb].forEach(v => v.addEventListener('timeupdate', () => { if (stopAt && v.currentTime >= stopAt.get(v)) v.pause(); }));
    const playEl = i => { const A = ea.rows[i], B = eb.rows[i]; if (!A || !B) return; stopAt = new Map([[va, A.end], [vb, B.end]]); va.currentTime = A.start; vb.currentTime = B.start; both(v => v.play().catch(() => {})); };
    const gantt = (name, e) => {
      const W = 100 / Math.max(ea.duration, eb.duration, 1);
      return h('div', { class: 'gantt' }, h('span', { class: 'gl' }, `${name} ${e.duration.toFixed(1)}초`), h('div', { class: 'gb' }, e.rows.map((r, i) => h('button', { class: 'gs g' + (i % 6), style: `left:${r.start * W}%;width:${(r.end - r.start) * W}%`, title: `${i + 1}. ${r.label} (${(r.end - r.start).toFixed(1)}초)`, onclick: () => playEl(i) }, String(i + 1)))));
    };
    const split = (vid, label) => h('button', { class: 'btn ghost js-split', onclick: act(async () => {
      await API(`versions/${vid}/elements`, 'POST', {});
      for (let i = 0; i < 600; i++) { const { jobs } = await API(`versions/${vid}/status`); const j = jobs.find(x => x.lang === 'split'); if (j?.state === 'done') return R.compare(); if (j?.state === 'failed') throw new Error(j.error); await new Promise(r => setTimeout(r, 1500)); }
    }) }, label + ' 요소 작업 분해');
    const why = h('div', { class: 'js-explain' });
    kids.push(h('div', { class: 'duo' }, va, vb),
      h('div', { class: 'row' }, h('button', { class: 'btn js-both', onclick: () => { stopAt = null; both(v => v.play().catch(() => {})); } }, '동시 재생'), h('button', { class: 'btn ghost', onclick: () => both(v => v.pause()) }, '일시정지'),
        h('button', { class: 'btn ghost', onclick: () => both(v => (v.currentTime = 0)) }, '처음으로'),
        h('button', { class: 'btn ghost', onclick: act(async () => { await API(`manuals/${av.manual_id}/standard`, 'POST', { version_id: +a0 }); toast('기준 영상을 표준으로 지정했습니다.'); }) }, '기준 영상을 표준으로')),
      h('section', { class: 'panel' }, h('h2', {}, '요소 작업'), h('p', { class: 'muted' }, '장면 전환과 10초 단위로 나눕니다. 막대를 누르면 두 영상의 같은 요소를 동시에 재생합니다.'),
        h('div', { class: 'row' }, split(a0, '기준'), split(b0, '비교')), ea.rows.length ? gantt('기준', ea) : null, eb.rows.length ? gantt('비교', eb) : null,
        ea.rows.length && eb.rows.length ? h('button', { class: 'btn js-explain-btn', onclick: act(async () => {
          why.replaceChildren(empty('분석 중…'));
          const r = await API('compare/explain', 'POST', { a: +a0, b: +b0 });
          put(why, h('p', {}, `전체: 기준 ${r.total.a}초, 비교 ${r.total.b}초 (${(r.total.b - r.total.a).toFixed(1)}초)`), r.text ? h('p', { class: 'note' }, r.text) : null,
            table(['요소', '내용', '기준', '비교', '차이'], r.diffs.map(d => [h('button', { class: 'lnk', onclick: () => playEl(d.ord) }, String(d.ord + 1)), d.label, d.a + '초', d.b + '초', h('b', { class: Math.abs(d.diff) >= 1 ? 'warn' : '' }, (d.diff > 0 ? '+' : '') + d.diff + '초')])));
        }) }, '차이 분석') : null, why),
      h('form', { class: 'row', onsubmit: act(async () => { await API('compare/notes', 'POST', { a: +a0, b: +b0, t: va.currentTime, memo: memo.value }); R.compare(); }) }, memo, h('button', { class: 'btn' }, '메모 추가')),
      notes.length ? table(['시점', '메모', '작성'], notes.map(n => [h('button', { class: 'lnk', onclick: () => both(v => (v.currentTime = n.t)) }, fmt(n.t)), n.memo, n.name])) : empty('메모가 없습니다.'));
    const title = input({ placeholder: '개선 과제', class: 'grow' }), who = sel([['', '담당자'], ...users.map(u => [u.id, u.name])]), due = input({ type: 'date' });
    const re = h('select', { multiple: true, size: 4 }, users.map(u => h('option', { value: u.id }, u.name)));
    kids.push(h('form', { class: 'panel', onsubmit: act(async () => { await API('tasks', 'POST', { title: title.value, manual_id: av.manual_id, assignee_id: who.value || null, due: due.value, retrain_user_ids: [...re.selectedOptions].map(o => +o.value) }); toast('과제를 등록했습니다.'); title.value = ''; }) },
      h('h2', {}, '개선 과제 등록'), field('과제', title), field('담당', who), field('기한', due), field('재교육 대상', re), h('button', { class: 'btn' }, '등록')));
  }
  page('작업 분석', kids);
};

R.tasks = async () => {
  const { tasks } = await API('tasks');
  page('개선 과제', tasks.length ? table(['과제', '매뉴얼', '담당', '기한', '상태'], tasks.map(t => [t.title, t.manual || '', t.assignee || '', t.due,
    sel([['open', '등록'], ['doing', '진행'], ['done', '완료']], t.status, { onchange: act(async e => API('tasks/' + t.id, 'PUT', { status: e.target.value })) })])) : empty('과제가 없습니다.'));
};

// ---------- 점검표 ----------
R.forms = async () => {
  const { forms } = await API('forms');
  const kids = [forms.length ? h('ul', { class: 'cards' }, forms.map(f => h('li', { class: 'mc' }, h('a', { href: '#/form/' + f.id }, h('b', {}, f.title), h('span', {}, f.site || '전체'))))) : empty('점검표가 없습니다.')];
  if (isMgr()) {
    const t = input({ placeholder: '점검표 이름' }), site = input({ placeholder: '사업장' }), list = h('div', {});
    const row = () => { const l = input({ placeholder: '항목', class: 'grow' }), ty = sel([['check', '합격/불합격'], ['number', '수치'], ['text', '메모']]), mn = input({ type: 'number', placeholder: '최소', class: 'n' }), mx = input({ type: 'number', placeholder: '최대', class: 'n' });
      const r = h('div', { class: 'row' }, l, ty, mn, mx, h('button', { type: 'button', class: 'btn ghost', onclick: () => r.remove() }, '삭제'));
      r._get = () => ({ label: l.value, type: ty.value, min: mn.value, max: mx.value }); list.append(r); };
    row();
    const src = input({ type: 'file', accept: '.pdf,.docx,.txt', class: 'js-ck-file' });
    const imp = h('button', { type: 'button', class: 'btn ghost js-ck-import', onclick: act(async () => {
      if (!src.files[0]) throw new Error('점검표 파일을 고르세요.');
      imp.disabled = true; imp.textContent = 'AI가 읽는 중…';
      try {
        const r = await fetch('api/ai/checklist', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/octet-stream' }, body: src.files[0] });
        const j = await r.json(); if (!r.ok) throw new Error(j.error);
        list.replaceChildren(); j.items.forEach(it => { row(); const r2 = list.lastChild; $$('input', r2)[0].value = it.label; $('select', r2).value = it.type; });
        if (!t.value) t.value = src.files[0].name.replace(/\.[^.]+$/, '');
        toast(`${j.items.length}개 항목을 가져왔습니다. 검토 후 저장하세요.`);
      } finally { imp.disabled = false; imp.textContent = '기존 점검표에서 항목 가져오기'; }
    }) }, '기존 점검표에서 항목 가져오기');
    kids.push(h('form', { class: 'panel', onsubmit: act(async () => { await API('forms', 'POST', { title: t.value, site: site.value, schema: [...list.children].map(r => r._get()) }); R.forms(); }) },
      h('h2', {}, '점검표 만들기'), h('div', { class: 'row' }, src, imp), field('이름', t), field('사업장', site), list, h('p', {}, h('button', { type: 'button', class: 'btn ghost', onclick: row }, '항목 추가'), ' ', h('button', { class: 'btn' }, '저장'))));
  }
  page('현장 점검표', kids);
};

R.form = async id => {
  const { forms } = await API('forms'); const f = forms.find(x => x.id == id);
  if (!f) return page('점검표', empty('찾을 수 없습니다.'));
  const inp = f.schema.map((it, i) => it.type === 'check' ? input({ type: 'checkbox', 'data-i': i }) : it.type === 'number' ? input({ type: 'number', step: 'any', 'data-i': i, inputmode: 'decimal' }) : input({ 'data-i': i }));
  const kids = [h('form', { class: 'panel', onsubmit: act(async e => {
    const values = {}; inp.forEach(el => (values[el.dataset.i] = el.type === 'checkbox' ? el.checked : el.value));
    const r = await API(`forms/${id}/submit`, 'POST', { values });
    toast(r.abnormal.length ? '이상 항목이 담당자에게 전달되었습니다.' : '정상 제출되었습니다.', !!r.abnormal.length); e.target.reset(); if (isMgr()) R.form(id);
  }) }, f.schema.map((it, i) => field(it.label + (it.type === 'number' && (it.min != null || it.max != null) ? ` (기준 ${it.min ?? ''}~${it.max ?? ''})` : ''), inp[i])), h('button', { class: 'btn wide' }, '제출'))];
  if (isMgr()) {
    const from = input({ type: 'date' }), to = input({ type: 'date' }), out = h('div', {});
    const load = async () => { const qs = `from=${from.value}&to=${to.value}`; const { rows } = await API(`forms/${id}/submissions?${qs}`);
      out.replaceChildren(dl(`api/forms/${id}/report.xlsx?${qs}`, '기간 기록 엑셀'), ' ', h('button', { class: 'btn ghost', onclick: () => print() }, '인쇄'),
        h('p', { class: 'muted' }, `제출 ${rows.length}건 · 이상 ${rows.filter(r => r.abnormal).length}건 (${rows.length ? Math.round(100 * rows.filter(r => r.abnormal).length / rows.length) : 0}%)`),
        ...f.schema.map((it, i) => it.type === 'number' && rows.length > 1 ? chart(it, rows.slice().reverse().map(r => ({ t: r.created, v: r.vals[i]?.value }))) || '' : ''),
        rows.length ? table(['시각', '점검자', '판정', ...f.schema.map(s => s.label), '승인'], rows.map(r => [r.created, r.name, r.abnormal ? badge('이상', 'bad') : badge('정상', 'ok'), ...r.vals.map(v => v.value === true ? '합격' : v.value === false ? '불합격' : String(v.value)),
          r.status === 'wait' ? h('span', {}, h('button', { class: 'btn ghost js-sub-ok', onclick: act(async () => { await API(`submissions/${r.id}/review`, 'POST', { ok: true }); load(); }) }, '승인'), ' ', h('button', { class: 'btn ghost', onclick: act(async () => { await API(`submissions/${r.id}/review`, 'POST', { ok: false }); load(); }) }, '반려')) : badge(r.status === 'ok' ? '승인' : '반려', r.status === 'ok' ? 'ok' : 'bad')])) : empty('기록이 없습니다.')); };
    from.onchange = to.onchange = act(load); load();
    kids.push(h('section', {}, h('h2', {}, '기록'), h('div', { class: 'row' }, from, to), out),
      h('button', { class: 'btn ghost', onclick: act(async () => { await API('forms/' + id, 'DELETE'); location.hash = '#/forms'; }) }, '점검표 보관'));
  }
  page(f.title, kids);
};

const chart = (it, pts) => {
  const vs = pts.map(p => +p.v).filter(v => !isNaN(v)); if (vs.length < 2) return null;
  const lo = Math.min(...vs, it.min ?? Infinity), hi = Math.max(...vs, it.max ?? -Infinity), W = 600, H = 160, P = 24;
  const X = i => P + i * (W - 2 * P) / (vs.length - 1), Y = v => H - P - (v - lo) * (H - 2 * P) / ((hi - lo) || 1);
  const ns = 'http://www.w3.org/2000/svg', el = (t, a) => { const e = document.createElementNS(ns, t); Object.entries(a).forEach(([k, v]) => e.setAttribute(k, v)); return e; };
  const svg = el('svg', { viewBox: `0 0 ${W} ${H}`, class: 'chart', role: 'img', 'aria-label': it.label + ' 추이' });
  [it.min, it.max].forEach(b => b != null && svg.append(el('line', { x1: P, x2: W - P, y1: Y(b), y2: Y(b), class: 'lim' })));
  svg.append(el('polyline', { points: vs.map((v, i) => `${X(i)},${Y(v)}`).join(' '), class: 'ln' }));
  vs.forEach((v, i) => { const c = el('circle', { cx: X(i), cy: Y(v), r: 4, class: (it.min != null && v < it.min) || (it.max != null && v > it.max) ? 'bad' : 'pt' }); const t = el('title', {}); t.textContent = `${pts[i].t}: ${v}`; c.append(t); svg.append(c); });
  return h('figure', { class: 'fig' }, h('figcaption', {}, it.label + ' 추이'), svg);
};

R.alerts = async () => {
  const { rows } = await API('alerts');
  page('이상 알림', rows.length ? table(['시각', '내용', ''], rows.map(a => [a.created, a.message, a.done ? '처리됨' : h('button', { class: 'btn ghost', onclick: act(async () => { await API(`alerts/${a.id}/done`, 'POST', {}); R.alerts(); nav(); }) }, '처리')])) : empty('알림이 없습니다.'));
};

// ---------- 중대재해 ----------
const KIND = { hazard: '유해·위험요인', budget: '안전보건 예산', evaluation: '책임자 평가', opinion: '종사자 의견', drill: '비상 대응 점검', contractor: '도급·위탁 평가', legal: '관계 법령 점검' };
const S_LBL = [['todo', '미착수'], ['doing', '진행'], ['done', '완료'], ['na', '해당 없음']];
R.safety = async () => {
  const hv = new URLSearchParams(location.hash.split('?')[1] || '').get('half') || '';
  const d = await API('safety' + (hv ? '?half=' + hv : ''));
  const y = +d.half.slice(0, 4), halves = [`${y - 1}H1`, `${y - 1}H2`, `${y}H1`, `${y}H2`, `${y + 1}H1`];
  const hs = sel(halves.map(x => [x, x.replace('H', '년 ') + '반기']), d.half, { onchange: e => (location.hash = '#/safety?half=' + e.target.value) });
  page('중대재해 의무 관리', h('p', { class: 'row' }, hs, dl(`api/safety/report.xlsx?half=${d.half}`, '반기 점검표 엑셀'), h('button', { class: 'btn ghost', onclick: () => print() }, '인쇄')),
    h('p', { class: 'muted' }, `근거: 중대재해 처벌 등에 관한 법률 시행령(대통령령, 2025-10-01 시행) 제4조·제5조. 완료 ${d.done}/${d.total}. 적용 여부와 충족 판단은 전문가 검토가 필요합니다.`),
    table(['조문', '의무', '주기', '증빙', '상태', '메모'], d.rows.map(r => {
      const st = sel(S_LBL, r.status), memo = input({ value: r.memo, placeholder: '메모' });
      const save = act(async () => { await API(`safety/${d.half}/${r.code}`, 'PUT', { status: st.value, memo: memo.value }); toast('저장했습니다.'); });
      st.onchange = memo.onchange = save;
      const ev = r.kind === 'edu' ? h('a', { href: '#/skills' }, `이수 ${r.evidence.done}/${r.evidence.total}`) : r.kind ? h('a', { href: '#/records/' + r.kind }, `${KIND[r.kind]} ${r.evidence}건`) : '';
      return [r.article, r.title, r.half ? '반기 1회 이상' : '', ev, st, memo];
    })));
};

R.records = async kind => {
  const { rows } = await API('records?kind=' + kind);
  const t = input({ placeholder: '제목' }), body = h('textarea', { rows: 3, placeholder: '내용' }), anon = input({ type: 'checkbox' });
  page(KIND[kind] || kind,
    h('form', { class: 'panel', onsubmit: act(async () => { await API('records', 'POST', { kind, data: { title: t.value, body: body.value, anon: anon.checked } }); R.records(kind); }) },
      field('제목', t), field('내용', body), kind === 'opinion' ? h('label', {}, anon, ' 익명으로 제출') : null, h('button', { class: 'btn' }, '등록')),
    rows.length ? table(['시각', '작성', '제목', '내용', '조치', '상태'], rows.map(r => {
      if (!isMgr()) return [r.created, r.name, r.data.title, r.data.body || '', r.data.action || '', r.status];
      const a = input({ value: r.data.action || '', placeholder: '조치 내용' }), st = sel([['open', '접수'], ['doing', '조치 중'], ['done', '완료']], r.status);
      a.onchange = st.onchange = act(async () => { await API('records/' + r.id, 'PUT', { status: st.value, action: a.value }); toast('저장했습니다.'); });
      return [r.created, r.name, r.data.title, r.data.body || '', a, st];
    })) : empty('기록이 없습니다.'));
};

R.usage = async () => {
  const d = await API('usage');
  const bars = (rows, key, label) => { const mx = Math.max(1, ...rows.map(r => r[key])); return h('div', { class: 'bars' }, rows.map(r => h('div', { class: 'bar' }, h('span', {}, r.day.slice(5)), h('i', { style: `width:${100 * r[key] / mx}%` }), h('b', {}, String(r[key]))))); };
  page('활용 현황', h('section', { class: 'panel' }, h('h2', {}, '매뉴얼별'), table(['매뉴얼', '종류', '상태', '열람자', '평균 시청', '이수', '배정', '마지막 열람'],
      d.manuals.map(m => [h('a', { href: '#/edit/' + m.id }, m.title), m.kind === 'doc' ? '문서' : '영상', m.status, m.viewers, (m.avg_pct ?? 0) + '%', m.completions, m.assigned, m.last_view || '']))),
    h('section', { class: 'panel' }, h('h2', {}, '최근 30일 로그인(일별 사용자 수)'), d.logins.length ? bars(d.logins, 'users') : empty('기록이 없습니다.')),
    h('section', { class: 'panel' }, h('h2', {}, '최근 30일 매뉴얼 열람'), d.views.length ? bars(d.views, 'n') : empty('기록이 없습니다.')));
};

// ---------- 승인·작성 계획 ----------
R.approvals = async () => {
  const { rows } = await API('approvals');
  page('승인 대기', rows.length ? table(['매뉴얼', '요청', '단계', '의견', ''], rows.map(r => {
    const c = input({ placeholder: '의견', class: 'grow' });
    const go = ok => act(async () => { const j = await API('approvals/' + r.id, 'POST', { ok, comment: c.value }); toast(ok ? (j.published ? '승인했고 공개되었습니다.' : '승인했습니다.') : '반려했습니다.'); R.approvals(); });
    return [h('a', { href: '#/play/' + r.manual_id }, r.title), r.requester, r.step + 1, c, h('span', {}, h('button', { class: 'btn js-approve', onclick: go(true) }, '승인'), ' ', h('button', { class: 'btn ghost', onclick: go(false) }, '반려'))];
  })) : empty('내 차례인 승인이 없습니다.'));
};

R.plans = async () => {
  const [{ rows }, { users }, { manuals }] = await Promise.all([API('plans'), API('users'), API('manuals')]);
  const t = input({ placeholder: '만들 매뉴얼', class: 'grow' }), who = sel([['', '담당'], ...users.map(u => [u.id, u.name])]), due = input({ type: 'date' });
  const ms = [['', '연결 안 함'], ...manuals.map(m => [m.id, m.title])];
  page('작성 계획', h('form', { class: 'row', onsubmit: act(async () => { await API('plans', 'POST', { title: t.value, owner_id: who.value || null, due: due.value }); R.plans(); }) }, t, who, due, h('button', { class: 'btn' }, '계획 추가')),
    h('p', { class: 'muted' }, `전체 ${rows.length} · 완료 ${rows.filter(r => r.status === 'done').length}`),
    rows.length ? table(['매뉴얼', '담당', '기한', '연결 매뉴얼', '상태'], rows.map(r => {
      const st = sel([['todo', '예정'], ['doing', '작성 중'], ['done', '완료']], r.status), mm = sel(ms, r.manual_id || '');
      st.onchange = mm.onchange = act(async () => { await API('plans/' + r.id, 'PUT', { status: st.value, manual_id: mm.value ? +mm.value : null }); toast('저장했습니다.'); });
      return [r.title, r.owner || '', r.due + (r.due && r.due < new Date().toISOString().slice(0, 10) && r.status !== 'done' ? ' (지남)' : ''), mm, st];
    })) : empty('계획이 없습니다.'));
};

// ---------- 스킬 맵 ----------
R.skillmap = async () => {
  const [d, { manuals }, { users }] = await Promise.all([API('skills/matrix'), API('manuals'), API('users')]);
  const L = d.levels;
  const cell = c => !c ? '-' : h('span', { class: 'lv lv' + c.level, title: `평가 ${L[c.level]}${c.self != null ? ' / 자기평가 ' + L[c.self] : ''}${c.target != null ? ' / 목표 ' + L[c.target] + ' ' + c.due : ''}` },
    `${c.level}${c.self != null ? '·' + c.self : ''}${c.target != null ? '→' + c.target : ''}`, c.late ? ' ⚠' : '');
  const name = input({ placeholder: '스킬 이름' }), cat = input({ placeholder: '분류' }), ms = h('select', { multiple: true, size: 4 }, manuals.map(m => h('option', { value: m.id }, m.title)));
  const uSel = sel(users.filter(u => u.active).map(u => [u.id, u.name])), sSel = sel(d.skills.map(k => [k.id, k.name])), lvSel = sel(L.map((t, i) => [i, `${i} ${t}`]), 0), cm = input({ placeholder: '평가 근거', class: 'grow' });
  const pSel = sel(d.skills.map(k => [k.id, k.name])), tSel = sel(L.map((t, i) => [i, `${i} ${t}`]), 3), pDue = input({ type: 'date' });
  const pUsers = h('select', { multiple: true, size: 4 }, users.filter(u => u.active).map(u => h('option', { value: u.id }, u.name))), pDept = sel([['', '부서 전체 선택'], ...[...new Set(users.map(u => u.dept).filter(Boolean))].map(x => [x, x])]);
  page('스킬 맵', h('p', { class: 'muted' }, '칸: 평가 수준·자기평가→목표. 0 미교육, 1 교육 중, 2 지도 하에 가능, 3 혼자 가능, 4 지도 가능. ⚠ 기한이 지났는데 목표 미달.'),
    h('p', { class: 'row' }, dl('api/skills/matrix.xlsx', '스킬 맵 엑셀')),
    d.skills.length ? table(['이름', '부서', ...d.skills.map(k => k.name)], d.users.map(u => [h('a', { href: '#/person/' + u.id }, u.name), u.dept, ...d.skills.map(k => cell(d.cells[`${u.id}:${k.id}`]))])) : empty('스킬을 먼저 만드세요.'),
    h('section', { class: 'panel' }, h('h2', {}, '평가 기록'), h('div', { class: 'row' }, uSel, sSel, lvSel, cm, h('button', { class: 'btn js-eval', onclick: act(async () => { await API('skills/eval', 'POST', { user_id: +uSel.value, skill_id: +sSel.value, level: +lvSel.value, comment: cm.value }); toast('평가를 기록했습니다.'); R.skillmap(); }) }, '기록'))),
    h('section', { class: 'panel' }, h('h2', {}, '교육 계획(목표·기한)'), field('스킬', pSel), field('목표 수준', tSel), field('기한', pDue), field('대상', pUsers), field('부서 전체', pDept),
      h('button', { class: 'btn js-plan', onclick: act(async () => { const r = await API('skills/plan', 'POST', { skill_id: +pSel.value, target: +tSel.value, due: pDue.value, user_ids: [...pUsers.selectedOptions].map(o => +o.value), dept: pDept.value }); toast(`${r.planned}명 계획을 세웠습니다.`); R.skillmap(); }) }, '계획 저장')),
    h('section', { class: 'panel' }, h('h2', {}, '마일스톤'), d.milestones.length ? table(['기한', '대상', '스킬', '목표'], d.milestones.map(x => [x.due, x.name, x.skill, L[x.target]])) : empty('계획이 없습니다.')),
    h('section', { class: 'panel' }, h('h2', {}, '스킬 목록'), d.skills.length ? table(['스킬', '분류', '연결 매뉴얼', ''], d.skills.map(k => {
      const n = input({ value: k.name }), c = input({ value: k.category || '' });
      const mm = h('select', { multiple: true, size: 3 }, manuals.map(x => h('option', { value: x.id, selected: (k.manual_ids || []).includes(x.id) }, x.title)));
      return [n, c, mm, h('span', {}, h('button', { class: 'btn ghost js-skill-save', onclick: act(async () => { await API('skills/' + k.id, 'PUT', { name: n.value, category: c.value, manual_ids: [...mm.selectedOptions].map(o => +o.value) }); toast('스킬을 고쳤습니다.'); }) }, '저장'), ' ',
        h('button', { class: 'btn ghost js-skill-del', onclick: act(async () => { if (!confirm(k.name + ' 스킬과 평가 기록을 지울까요?')) return; await API('skills/' + k.id, 'DELETE'); R.skillmap(); }) }, '삭제'))];
    })) : empty('스킬이 없습니다.')),
    h('section', { class: 'panel' }, h('h2', {}, '스킬 만들기'), field('이름', name), field('분류', cat), field('연결 매뉴얼', ms),
      h('button', { class: 'btn js-skill-new', onclick: act(async () => { await API('skills', 'POST', { name: name.value, category: cat.value, manual_ids: [...ms.selectedOptions].map(o => +o.value) }); R.skillmap(); }) }, '스킬 추가')));
};

const personView = async (d, self) => {
  const L = d.levels;
  page(self ? '내 스킬' : d.user.name + ' 스킬', d.skills.length ? d.skills.map(k => {
    const cur = k.history.find(x => x.kind === 'eval'), mine = k.history.find(x => x.kind === 'self');
    const lv = sel(L.map((t, i) => [i, `${i} ${t}`]), mine ? mine.level : 0), cm = input({ placeholder: '자기평가 메모', class: 'grow' });
    return h('section', { class: 'panel' }, h('h2', {}, `${k.name} `, badge(cur ? L[cur.level] : '평가 없음', cur && cur.level >= 3 ? 'ok' : '')),
      k.plan ? h('p', {}, `목표: ${L[k.plan.target]} (기한 ${k.plan.due})`) : null,
      h('p', { class: 'muted' }, '교육 이력: ' + (k.education.map(e => `${e.title} ${e.created.slice(0, 10)}`).join(', ') || '없음')),
      k.history.length ? table(['시각', '구분', '수준', '평가자', '메모'], k.history.map(x => [x.created, x.kind === 'self' ? '자기평가' : '평가', L[x.level], x.by_name, x.comment])) : null,
      self ? h('div', { class: 'row' }, lv, cm, h('button', { class: 'btn ghost js-self', onclick: act(async () => { await API('skills/self', 'POST', { skill_id: k.id, level: +lv.value, comment: cm.value }); toast('자기평가를 남겼습니다.'); R.myskills(); }) }, '자기평가 저장')) : null);
  }) : empty('등록된 스킬이 없습니다.'));
};
R.myskills = async () => personView(await API('skills/me'), true);
R.person = async id => personView(await API('skills/user/' + id), false);

// ---------- 보안 설정 ----------
R.security = async () => {
  const [d, pol] = await Promise.all([API('settings/security'), API('settings/policy')]);
  const appr = input({ type: 'checkbox', checked: pol.approval_required, class: 'js-approval-required' });
  appr.onchange = act(async () => { await API('settings/policy', 'PUT', { approval_required: appr.checked }); toast(appr.checked ? '승인을 마친 버전만 공개됩니다.' : '승인 없이도 공개할 수 있습니다.'); });
  const ips = input({ value: d.allowed_ips, class: 'grow', placeholder: '비우면 제한 없음. 예: 203.0.113.0/24, 198.51.100.7' });
  page('보안 설정', h('section', { class: 'panel' }, h('h2', {}, '배포 승인'), h('label', {}, appr, ' 매뉴얼은 승인을 마친 버전만 공개하고, 공개된 매뉴얼을 고치면(새 버전) 다시 승인받기 전까지 공개를 멈춥니다.')),
    h('section', { class: 'panel' }, h('h2', {}, '접속 IP 제한'), h('p', { class: 'muted' }, `지금 접속한 IP: ${d.my_ip}. 목록에 없으면 저장되지 않습니다.`), ips,
    h('p', {}, h('button', { class: 'btn', onclick: act(async () => { await API('settings/security', 'PUT', { allowed_ips: ips.value }); toast('저장했습니다.'); }) }, '저장'))),
    h('section', { class: 'panel' }, h('h2', {}, '백업'), h('p', { class: 'muted' }, '하루 한 번 자동 백업하고 최근 14개를 보관합니다.'), d.backups.length ? h('p', {}, '보관 중: ' + d.backups.join(', ')) : null,
      h('form', { method: 'post', action: 'api/backup' }, h('button', { class: 'btn ghost', type: 'button', onclick: act(async () => {
        const r = await fetch('api/backup', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: '{}' });
        if (!r.ok) throw new Error('백업하지 못했습니다.');
        const a = h('a', { href: URL.createObjectURL(await r.blob()), download: 'safeclip-backup.db' }); a.click(); toast('백업 파일을 내려받았습니다.');
      }) }, '지금 백업 내려받기'))));
};

// ---------- 계정·기록 ----------
R.users = async () => {
  const { users } = await API('users');
  const bulk = h('textarea', { rows: 4, placeholder: '한 줄에 한 명: 아이디,이름,부서,사업장,언어코드,권한(worker/manager/admin),이메일' }), out = h('div', {});
  const kids = [];
  if (isAdmin()) kids.push(h('form', { class: 'panel', onsubmit: act(async () => {
    const rows = bulk.value.split('\n').map(l => l.trim()).filter(Boolean).map(l => { const [login, name, dept, site, lang, role, email] = l.split(',').map(x => x.trim()); return { login, name, dept, site, lang, role, email }; });
    const r = await API('users', 'POST', { users: rows });
    out.replaceChildren(h('p', { class: 'muted' }, '임시 비밀번호는 지금만 표시됩니다.'), table(['아이디', '임시 비밀번호'], r.created.map(c => [c.login, c.password])));
    bulk.value = '';
  }) }, h('h2', {}, '사용자 추가'), bulk, h('button', { class: 'btn' }, '추가'), out));
  const pending = users.filter(u => !u.active && (u.pending || (!u.has_pw && u.links.length)));
  if (pending.length) kids.push(h('p', { class: 'warn' }, `가입 신청 ${pending.length}건: 활성에 체크하면 승인됩니다.`));
  kids.push(table(['이름', '아이디', '이메일', '로그인', '부서', '사업장', '언어', '권한', '활성', ''], users.map(u => {
    const r = sel([['worker', '작업자'], ['manager', '관리자'], ['admin', '전체 관리자']], u.role, { disabled: !isAdmin() });
    const a = input({ type: 'checkbox', checked: !!u.active, disabled: !isAdmin() });
    r.onchange = a.onchange = act(async () => { await API('users/' + u.id, 'PUT', { role: r.value, active: a.checked }); toast('저장했습니다.'); });
    return [u.name, u.login, u.email || '', [u.has_pw ? '비밀번호' : '', ...u.links].filter(Boolean).join(', ') + (!u.active && (u.pending || !u.has_pw) ? ' (가입 신청)' : '') + (u.totp ? ' · 2단계' : ''), u.dept, u.site, LANGS[u.lang] || u.lang, r, a, isAdmin() ? h('button', { class: 'btn ghost', onclick: act(async () => { const j = await API(`users/${u.id}/reset`, 'POST', {}); out.replaceChildren(h('p', {}, `${u.login} 임시 비밀번호: ${j.password}`)); }) }, '비밀번호 재설정') : ''];
  })));
  if (isAdmin()) kids.push(await permsBox());
  page('사용자', kids);
};

R.audit = async () => {
  const { rows } = await API('audit');
  page('접속 기록', dl('api/audit.xlsx', '엑셀'), table(['시각', '사용자', '행위', '대상', 'IP'], rows.map(r => [r.created, r.name || '', r.action, r.target, r.ip])));
};

R.glossary = async () => {
  const { rows } = await API('glossary');
  const t = input({ placeholder: '인식 결과' }), w = input({ placeholder: '바꿀 말' });
  page('용어 사전', h('form', { class: 'row', onsubmit: act(async () => { await API('glossary', 'POST', { term: t.value, replace_with: w.value }); R.glossary(); }) }, t, w, h('button', { class: 'btn' }, '추가')),
    table(['인식 결과', '바꿀 말', ''], rows.map(r => [r.term, r.replace_with, h('button', { class: 'btn ghost', onclick: act(async () => { await API('glossary/' + r.id, 'DELETE'); R.glossary(); }) }, '삭제')])));
};

R.login = async () => {
  const d = await API('settings/login');
  const base = input({ value: d.base_url, class: 'grow' }), owner = input({ value: d.owner_email, class: 'grow', placeholder: '관리자로 바로 들어올 이메일 (쉼표로 여러 개)' });
  const rows = d.providers.map(p => {
    const cid = input({ value: p.cid, placeholder: '클라이언트 ID', class: 'grow' }), key = input({ type: 'password', placeholder: p.has_key ? '저장됨 (바꿀 때만 입력)' : '클라이언트 보안 키', class: 'grow', autocomplete: 'off' });
    return { p, cid, key, el: h('section', { class: 'panel' }, h('h2', {}, p.label + ' ', p.cid && p.has_key ? badge('사용 중', 'ok') : badge('미설정')),
      h('p', { class: 'muted' }, '개발자 콘솔에 등록할 리디렉션 URI: ', h('code', {}, p.redirect_uri), ' ', h('a', { href: p.console, target: '_blank', rel: 'noopener' }, '콘솔 열기')),
      field('클라이언트 ID', cid), field('클라이언트 보안 키', key),
      p.id === 'sso' ? (() => { p._x = {}; return ['issuer', 'domain', 'label'].map(k => { const el = input({ value: (k === 'label' ? p.sso_label : p[k]) || '', class: 'grow', placeholder: { issuer: '발급자 주소 (예: https://login.microsoftonline.com/<테넌트>/v2.0)', domain: '회사 이메일 도메인 (예: pkconst.co.kr) — 이 도메인은 바로 근로자로 가입', label: '로그인 버튼 이름 (예: 피케이건설 계정)' }[k] }); p._x[k] = el; return field({ issuer: '발급자(issuer)', domain: '회사 도메인', label: '버튼 이름' }[k], el); }); })() : null) };
  });
  page('로그인 설정', h('section', { class: 'panel' }, field('서비스 주소 (리디렉션 URI의 앞부분)', base), field('대표 이메일', owner)), rows.map(r => r.el),
    h('button', { class: 'btn js-save-login', onclick: act(async () => {
      const body = { base_url: base.value, owner_email: owner.value };
      rows.forEach(r => (body[r.p.id] = { cid: r.cid.value, key: r.key.value, ...(r.p._x ? Object.fromEntries(Object.entries(r.p._x).map(([k, el]) => [k, el.value])) : {}) }));
      await API('settings/login', 'PUT', body); toast('저장했습니다. 로그인 화면에 바로 반영됩니다.'); R.login();
    }) }, '저장'));
};

R.leads = async () => {
  const { leads } = await API('leads');
  page('접수 내역', dl('api/leads.csv', 'CSV'), leads.length ? table(['시각', '종류', '내용', '상태'], leads.map(l => [l.created, l.kind, Object.entries(l.data).map(([k, v]) => k + ': ' + v).join(' / '),
    sel([['new', '신규'], ['done', '처리']], l.status, { onchange: act(async e => API(`leads/${l.id}/status`, 'POST', { status: e.target.value })) })])) : empty('접수가 없습니다.'));
};

R.home = async () => {
  if (!isMgr()) return R.my();
  const d = await API('dashboard');
  const tile = (t, v, href, warn) => h('a', { class: 'tile' + (warn ? ' warnt' : ''), href }, h('span', {}, t), h('b', {}, v));
  const nt = await API('notices');
  page('현황', noticeBar(nt.rows), h('div', { class: 'tiles' },
    tile('교육 이수', `${d.edu.done}/${d.edu.total}`, '#/skills'), tile('기한 경과', d.overdue, '#/skills', d.overdue > 0), tile(`${d.half.replace('H', '년 ')}반기 의무`, `${d.safety_done}/${d.safety_total}`, '#/safety'),
    tile('이상 알림', d.alerts, '#/alerts', d.alerts > 0), tile('미조치 위험요인', d.hazards, '#/records/hazard', d.hazards > 0), tile('개선 과제', d.tasks, '#/tasks'), tile('공개 매뉴얼', d.manuals, '#/manuals'), tile('사용자', d.users, '#/users')));
};

R.password = async () => {
  const o = input({ type: 'password', autocomplete: 'current-password' }), n = input({ type: 'password', autocomplete: 'new-password' });
  const linked = PROVIDERS.map(p => ME.links.includes(p.id)
    ? h('p', {}, badge(p.label + ' 연결됨', 'ok'), ' ', h('button', { class: 'btn ghost', onclick: act(async () => { await API('me/links/' + p.id, 'DELETE'); ME.links = ME.links.filter(x => x !== p.id); R.password(); }) }, '연결 끊기'))
    : h('p', {}, h('a', { class: 'sbtn sbtn-' + p.id, href: `auth/${p.id}/start?link=1` }, p.label + ' 계정 연결')));
  page('계정·비밀번호', ME.must_change ? h('p', { class: 'warn' }, '처음 로그인했습니다. 비밀번호를 바꿔 주세요.') : null, h('form', { class: 'panel', onsubmit: act(async () => { await API('me/password', 'POST', { old: o.value, new: n.value }); toast('변경했습니다. 다시 로그인하세요.'); setTimeout(() => (location.href = 'login.html'), 800); }) },
    ME.has_pw ? field('현재 비밀번호', o) : h('p', { class: 'muted' }, '소셜 로그인 계정입니다. 비밀번호를 만들면 아이디로도 로그인할 수 있습니다.'), field('새 비밀번호 (8자 이상)', n), h('button', { class: 'btn' }, ME.has_pw ? '변경' : '비밀번호 만들기')),
    PROVIDERS.length ? h('section', { class: 'panel' }, h('h2', {}, '소셜 계정 연결'), h('p', { class: 'muted' }, '연결하면 다음부터 해당 계정으로 바로 로그인합니다.'), linked) : null,
    tfaBox());
};
const tfaBox = () => {
  const code = input({ inputmode: 'numeric', placeholder: '6자리 코드', class: 'n js-otp-code' }), out = h('div', {});
  if (ME.totp) return h('section', { class: 'panel' }, h('h2', {}, '2단계 인증 ', badge('사용 중', 'ok')), h('div', { class: 'row' }, code,
    h('button', { class: 'btn ghost', onclick: act(async () => { await API('me/2fa/disable', 'POST', { code: code.value }); ME.totp = false; toast('2단계 인증을 껐습니다.'); R.password(); }) }, '끄기')));
  return h('section', { class: 'panel' }, h('h2', {}, '2단계 인증'), h('p', { class: 'muted' }, '로그인할 때 인증 앱(Google Authenticator 등)의 6자리 코드를 한 번 더 확인합니다.'), out,
    h('button', { class: 'btn ghost js-2fa-setup', onclick: act(async () => {
      const j = await API('me/2fa/setup', 'POST', {});
      out.replaceChildren(h('p', {}, '인증 앱에 아래 키를 입력하거나, 휴대폰에서 링크를 누르세요.'), h('p', {}, h('code', { class: 'js-2fa-key' }, j.key)), h('p', {}, h('a', { href: j.uri }, '인증 앱에 추가')),
        h('div', { class: 'row' }, code, h('button', { class: 'btn js-2fa-on', onclick: act(async () => { await API('me/2fa/enable', 'POST', { code: code.value }); ME.totp = true; toast('2단계 인증을 켰습니다.'); R.password(); }) }, '확인하고 켜기')));
    }) }, '2단계 인증 켜기'));
};

function nav() {
  const a = (href, t) => h('a', { href }, t);
  const items = [a('#/home', isMgr() ? '현황' : '내 교육'), ...(isMgr() ? [a('#/my', '내 교육')] : []), a('#/manuals', '매뉴얼'), a('#/myskills', '내 스킬'), a('#/forms', '점검표'), ...(SAFETY ? [a('/voice', '근로자 의견·위험 신고')] : [a('#/records/hazard', '위험요인 신고'), a('#/records/opinion', '의견 제출')]), a('#/tasks', '개선 과제')];
  if (isMgr()) items.push(a('#/approvals', '승인 대기'), a('#/plans', '작성 계획'), a('#/courses', '교육 과정'), a('#/skillmap', '스킬 맵'), a('#/skills', '교육 이수 현황'), a('#/education', '교육 기록'), a('#/usage', '활용 현황'), a('#/compare', '작업 분석'), a('#/reports', '보고서'), a('#/onboarding', '도입 관리'), a('#/folders', '폴더'), a('#/alerts', '이상 알림' + (ALERTS ? ` (${ALERTS})` : '')), ...(SAFETY ? [a('/', '안전보건 현황'), a('/duty', '중대재해 의무'), a('/search', '법령 검색'), a('/cases', '사고사례')] : [a('#/safety', '중대재해 의무')]), a('#/users', '사용자'), a('#/glossary', '용어 사전'), a('#/leads', '접수 내역'));
  if (isAdmin()) items.push(a('#/audit', '접속 기록'), a('#/login', '로그인 설정'), a('#/security', '보안 설정'));
  items.push(a('#/password', '계정'), h('button', { class: 'lnk', onclick: act(async () => { await API('logout', 'POST', {}); if ('caches' in window) await caches.delete('safeclip-offline'); location.href = 'login.html'; }) }, `로그아웃 (${ME.name})`));
  navEl.replaceChildren(...items);
  $$('a', navEl).forEach(x => x.classList.toggle('on', x.getAttribute('href') === location.hash.split('?')[0]));
}

async function go() {
  const [, name = 'home', arg] = (location.hash.split('?')[0]).split('/');
  try {
    if (ME.must_change && name !== 'password') { location.hash = '#/password'; return; }
    nav();
    await (R[name] || R.home)(arg);
  } catch (e) { view.replaceChildren(h('p', { class: 'warn' }, e.message)); }
  scrollTo(0, 0);
}

(async () => {
  const j = await API('me'); ME = j.user; LANGS = j.langs; PROVIDERS = j.providers; ALERTS = j.alerts; SAFETY = j.safety;
  addEventListener('hashchange', go); go();
  if ('serviceWorker' in navigator) navigator.serviceWorker.register('sw.js').catch(() => {});
  // 이상 알림 수를 30초마다 새로 읽는다
  if (isMgr()) setInterval(() => API('me').then(r => { if (r.alerts !== ALERTS) { if (r.alerts > ALERTS) toast(`새 이상 알림 ${r.alerts - ALERTS}건`, true); ALERTS = r.alerts; nav(); } }).catch(() => {}), 30000);
})();
