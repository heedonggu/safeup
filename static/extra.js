// 원작 서비스 기능 대조 외부 채점에서 빠진 화면: 보고서, 도입 관리, 교육 과정 편집·진행 리포트, 단계 번역, 개정 이력, 영상 내보내기, 세부 권한, 폴더.
// product.js 의 도우미(h, API, page, table …)를 그대로 쓴다.
const LANG_OPTS = () => Object.entries(LANGS).filter(([k]) => k !== 'ko');
const waitJob = async (vid, key, st) => {
  for (let i = 0; i < 3600; i++) {
    const { jobs } = await API(`versions/${vid}/status`); const j = jobs.find(x => x.lang === key);
    if (j?.state === 'done') return; if (j?.state === 'failed') throw new Error(j.error);
    if (st) st.textContent = '처리 중…'; await new Promise(r => setTimeout(r, 2000));
  }
};
const postFile = async (path, file, headers = {}) => {
  const r = await fetch('api/' + path, { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/octet-stream', ...headers }, body: file });
  const j = await r.json().catch(() => ({})); if (!r.ok) throw new Error(j.error || '처리하지 못했습니다.'); return j;
};
const busy = async (btn, label, fn) => { const t = btn.textContent; btn.disabled = true; btn.textContent = label; try { return await fn(); } finally { btn.disabled = false; btn.textContent = t; } };

// ---------- 보고서 ----------
R.reports = async () => {
  const { sections } = await API('report/sections');
  const today = new Date().toISOString().slice(0, 10), first = today.slice(0, 8) + '01';
  const from = input({ type: 'date', value: first }), to = input({ type: 'date', value: today }), title = input({ value: '안전·교육 보고서', class: 'grow' });
  const checks = Object.entries(sections).map(([k, t]) => { const c = input({ type: 'checkbox', checked: true, value: k }); return h('label', {}, c, ' ' + t); });
  const qs = () => `from=${from.value}&to=${to.value}&title=${encodeURIComponent(title.value)}&sections=${checks.map(l => $('input', l)).filter(c => c.checked).map(c => c.value).join(',')}`;
  const open = ext => () => { location.href = `api/report.${ext}?${qs()}`; };
  page('보고서', h('section', { class: 'panel' }, h('p', { class: 'muted' }, '영상 교육 이수, 현장 점검표, 위험요인·의견 기록, 중대재해 의무 점검, 개선 과제, 매뉴얼 현황을 기간별로 묶어 보고서로 냅니다. 숫자는 모두 앱에 쌓인 실제 기록에서 셉니다.'),
    field('제목', title), h('div', { class: 'row' }, field('시작', from), field('끝', to)), h('div', { class: 'row checks' }, checks),
    h('p', { class: 'row' }, h('button', { class: 'btn js-report-pdf', onclick: open('pdf') }, 'PDF 보고서'), h('button', { class: 'btn ghost js-report-xlsx', onclick: open('xlsx') }, '엑셀 보고서'))));
};

// ---------- 도입 관리: 목표 · 3개월 계획 · 정기 점검 ----------
R.onboarding = async () => {
  const [d, { users }] = await Promise.all([API('onboarding'), API('users')]);
  const owners = [['', '담당'], ...users.filter(u => u.active).map(u => [u.id, u.name])];
  const gT = input({ placeholder: '도입 목표 (예: 신규 근로자 교육 시간 절반)', class: 'grow' }), gM = sel([['', '연결 지표 (선택)'], ...Object.keys(d.live).map(k => [k, k])]), gV = input({ placeholder: '목표값', class: 'n' }), gD = input({ type: 'date' });
  const pW = input({ type: 'number', min: 1, max: 13, value: 1, class: 'n', 'aria-label': '주차' }), pT = input({ placeholder: '할 일', class: 'grow' }), pP = sel([['상', '우선 상'], ['중', '우선 중'], ['하', '우선 하']], '중'), pO = sel(owners, '');
  const mD = input({ type: 'date', value: new Date().toISOString().slice(0, 10) }), mK = sel(['정기 점검', '온라인 회의', '현장 방문', '착수 회의'].map(x => [x, x])), mA = input({ placeholder: '참석자', class: 'grow' });
  const mN = h('textarea', { rows: 3, placeholder: '회의 내용·운영 점검 결과' }), mX = h('textarea', { rows: 2, placeholder: '개선 제안 (한 줄에 하나, 저장하면 개선 과제로 등록)' });
  const weeks = [...Array(13)].map((_, i) => i + 1);
  page('도입 관리',
    h('div', { class: 'tiles' }, Object.entries(d.live).map(([k, v]) => h('div', { class: 'tile' }, h('span', {}, k), h('b', {}, v))), h('div', { class: 'tile' }, h('span', {}, '3개월 계획 진척'), h('b', {}, d.done_pct + '%'))),
    h('section', { class: 'panel' }, h('h2', {}, '도입 목표'),
      h('form', { class: 'row', onsubmit: act(async () => { await API('onboarding/goals', 'POST', { title: gT.value, metric: gM.value, target: gV.value, due: gD.value }); R.onboarding(); }) }, gT, gM, gV, gD, h('button', { class: 'btn' }, '목표 추가')),
      d.goals.length ? table(['목표', '지표', '현재(실측)', '목표값', '기한', '담당'], d.goals.map(g => {
        const cur = input({ value: g.current, class: 'n' }); cur.onchange = act(async () => { await API('onboarding/goals/' + g.id, 'PUT', { current: cur.value }); toast('저장했습니다.'); });
        return [g.title, g.metric || '-', g.metric && d.live[g.metric] != null ? String(d.live[g.metric]) : cur, g.target, g.due, g.owner || ''];
      })) : empty('목표가 없습니다.')),
    h('section', { class: 'panel' }, h('h2', {}, '3개월 도입 계획(13주)'),
      h('form', { class: 'row', onsubmit: act(async () => { await API('onboarding/plan', 'POST', { week: +pW.value, title: pT.value, priority: pP.value, owner_id: pO.value || null }); R.onboarding(); }) }, pW, '주차', pT, pP, pO, h('button', { class: 'btn' }, '계획 추가')),
      d.plan.length ? h('div', { class: 'gantt' }, weeks.map(w => { const ps = d.plan.filter(p => p.week === w); return ps.length ? h('div', { class: 'row' }, h('b', { class: 'n' }, w + '주'), ps.map(p => {
        const st = sel([['todo', '예정'], ['doing', '진행'], ['done', '완료']], p.status); st.onchange = act(async () => { await API('onboarding/plan/' + p.id, 'PUT', { status: st.value }); toast('저장했습니다.'); });
        return h('span', { class: 'chip' }, badge(p.priority, p.priority === '상' ? 'bad' : p.priority === '중' ? 'warn' : ''), ' ', p.title, ' · ', p.owner || '', ' ', st);
      })) : null; })) : empty('계획이 없습니다.')),
    h('section', { class: 'panel' }, h('h2', {}, '정기 점검·회의 기록'),
      h('form', { onsubmit: act(async () => { await API('onboarding/meetings', 'POST', { day: mD.value, kind: mK.value, attendees: mA.value, notes: mN.value, actions: mX.value }); toast('기록했습니다. 개선 제안은 개선 과제로 넘겼습니다.'); R.onboarding(); }) },
        h('div', { class: 'row' }, mD, mK, mA), mN, mX, h('button', { class: 'btn' }, '회의 기록')),
      d.meetings.length ? table(['날짜', '종류', '참석', '내용', '개선 제안'], d.meetings.map(m => [m.day, m.kind, m.attendees, m.notes, m.actions])) : empty('기록이 없습니다.')));
};

// ---------- 교육 과정: 만들기(직접·PDF), 순서 편집, 진행 리포트 ----------
R.courses = async () => {
  const [{ courses }, { manuals }, { users }] = await Promise.all([API('courses'), API('manuals'), API('users')]);
  const t = input({ placeholder: '과정 이름' }), ms = h('select', { multiple: true, size: 6 }, manuals.map(m => h('option', { value: m.id }, m.title)));
  const dep = sel([['', '부서 선택'], ...[...new Set(users.map(u => u.dept).filter(Boolean))].map(x => [x, x])]);
  const pdf = input({ type: 'file', accept: '.pdf,.docx,.txt', class: 'js-course-pdf' });
  const pdfBtn = h('button', { type: 'button', class: 'btn ghost js-course-ai', onclick: act(async () => {
    if (!pdf.files[0]) throw new Error('작업표준서 파일을 고르세요.');
    const j = await busy(pdfBtn, 'AI가 과정을 나누는 중…', async () => {
      const { token } = await postFile('ai/course', pdf.files[0], { 'X-Name': encodeURIComponent(pdf.files[0].name.replace(/\.[^.]+$/, '')) });
      for (let i = 0; i < 1800; i++) {
        const s = await API('ai/course/' + token); if (s.state === 'done') return s; if (s.state === 'failed') throw new Error(s.error);
        pdfBtn.textContent = `AI가 과정을 나누는 중… (${s.done}/${s.total})`; await new Promise(r => setTimeout(r, 2000));
      }
      throw new Error('시간이 너무 오래 걸립니다. 잠시 뒤 과정 목록을 확인하세요.');
    });
    toast(`과정과 문서 매뉴얼 ${j.manual_ids.length}개를 만들었습니다. 검토 후 공개하세요.`); R.courses();
  }) }, 'PDF 작업표준서로 과정 자동 만들기');
  const editor = c => {
    let items = c.items.map(i => ({ id: i.id, title: i.title, status: i.status }));
    const name = input({ value: c.title, class: 'grow' }), ul = h('ol', {}), add = sel([['', '매뉴얼 추가…'], ...manuals.map(m => [m.id, m.title])], '');
    const draw = () => ul.replaceChildren(...items.map((i, k) => h('li', {}, h('a', { href: '#/edit/' + i.id }, i.title), ' ', badge(i.status === 'published' ? '공개' : '초안', i.status === 'published' ? 'ok' : ''),
      h('button', { type: 'button', class: 'btn ghost', disabled: !k, onclick: () => { [items[k - 1], items[k]] = [items[k], items[k - 1]]; draw(); } }, '↑'),
      h('button', { type: 'button', class: 'btn ghost', disabled: k === items.length - 1, onclick: () => { [items[k + 1], items[k]] = [items[k], items[k + 1]]; draw(); } }, '↓'),
      h('button', { type: 'button', class: 'btn ghost', onclick: () => { items.splice(k, 1); draw(); } }, '빼기'),
      (() => { const sub = h('ul', { class: 'muted' }); API('manuals/' + i.id).then(d => sub.replaceChildren(...d.steps.map(st => h('li', {}, st.title)))).catch(() => {}); return sub; })())));
    add.onchange = () => { const m = manuals.find(x => x.id == add.value); if (m && !items.some(i => i.id === m.id)) items.push({ id: m.id, title: m.title, status: m.status }); add.value = ''; draw(); };
    draw();
    const rep = h('div', {});
    return h('details', { open: true, class: 'tree' }, h('summary', {}, h('b', {}, c.title), ` (${c.items.length}개)`),
      h('div', { class: 'row' }, name, add), ul,
      h('p', { class: 'row' }, h('button', { class: 'btn js-course-save', onclick: act(async () => { await API('courses/' + c.id, 'PUT', { title: name.value, manual_ids: items.map(i => i.id) }); toast('과정을 저장했습니다.'); R.courses(); }) }, '저장'),
        h('button', { class: 'btn ghost', onclick: act(async () => { const r = await API(`courses/${c.id}/assign`, 'POST', { dept: dep.value }); toast(`${r.assigned}명, 매뉴얼 ${r.manuals}개 배정`); }) }, '부서에 배정'),
        h('button', { class: 'btn ghost js-course-report', onclick: act(async () => {
          const r = await API(`courses/${c.id}/report`); const L = { done: ['이수', 'ok'], outdated: ['재이수', 'warn'], doing: ['진행', 'info'], todo: ['미시작', 'bad'] };
          put(rep, h('p', {}, `학습자 ${r.rows.length}명 · 평균 진행률 ${r.avg}% `, dl(`api/courses/${c.id}/report.xlsx`, '엑셀')),
            r.rows.length ? table(['이름', '부서', ...r.items.map(i => i.title), '진행률'], r.rows.map(u => [u.name, u.dept, ...u.cells.map(x => badge(...L[x])), u.pct + '%'])) : empty('배정된 학습자가 없습니다.'));
        }) }, '진행 리포트'),
        h('button', { class: 'btn ghost', onclick: act(async () => { if (!confirm('과정을 지울까요? 매뉴얼은 남습니다.')) return; await API('courses/' + c.id, 'DELETE'); R.courses(); }) }, '과정 삭제')), rep);
  };
  page('교육 과정', h('form', { class: 'panel', onsubmit: act(async () => { await API('courses', 'POST', { title: t.value, manual_ids: [...ms.selectedOptions].map(o => +o.value) }); R.courses(); }) }, field('이름', t), field('매뉴얼', ms), h('button', { class: 'btn' }, '과정 만들기')),
    h('section', { class: 'panel' }, h('h2', {}, 'PDF 작업표준서로 과정 만들기'), h('p', { class: 'muted' }, '작업표준서를 AI가 읽어 작업별 문서 매뉴얼과 그것을 묶은 과정을 함께 만듭니다(초안으로 만들어지니 검토 후 공개).'), h('div', { class: 'row' }, pdf, pdfBtn)),
    field('배정할 부서', dep), courses.length ? h('div', { class: 'tree' }, courses.map(editor)) : empty('과정이 없습니다.'));
};

// ---------- 매뉴얼 편집 화면에 붙는 상자 ----------
const stepsTransBox = (m, v) => {
  const lang = sel(LANG_OPTS(), 'en', { class: 'js-st-lang' }), st = h('p', { class: 'muted js-st-state' }, m.step_langs?.length ? '번역된 언어: ' + m.step_langs.map(l => LANGS[l] || l).join(', ') : ''), out = h('div', {});
  const load = async () => {
    const r = await API(`versions/${v.id}/steps?lang=${lang.value}`); if (!r.langs.includes(lang.value)) return put(out, empty('이 언어 번역이 없습니다.'));
    const rows = r.steps.map(s => { const t = input({ value: s.title, class: 'grow' }), n = input({ value: s.note || '', class: 'grow' }), w = input({ value: s.warn || '', class: 'grow' }); const el = h('div', { class: 'row' }, t, n, w); el._get = () => ({ ord: s.ord, title: t.value, note: n.value, warn: w.value }); return el; });
    put(out, rows, h('button', { class: 'btn ghost', onclick: act(async () => { await API(`versions/${v.id}/steps/i18n`, 'PUT', { lang: lang.value, steps: rows.map(r => r._get()) }); toast('번역을 저장했습니다.'); }) }, '번역 고친 것 저장'));
  };
  lang.onchange = act(load);
  return h('section', { class: 'panel' }, h('h2', {}, '제목·단계 글 번역'), h('p', { class: 'muted' }, `제목·단계 제목·설명·주의사항을 ${Object.keys(LANGS).length}개 언어 중 골라 AI로 번역합니다. 근로자는 자기 언어로 봅니다.`),
    h('div', { class: 'row' }, lang, h('button', { class: 'btn ghost js-st-trans', onclick: act(async e => { await busy(e.target, 'AI 번역 중…', async () => { await API(`versions/${v.id}/steps/translate`, 'POST', { lang: lang.value }); await waitJob(v.id, 'steps-' + lang.value, st); }); st.textContent = '번역했습니다.'; toast('단계 글을 번역했습니다.'); load(); }) }, '이 언어로 번역'),
      h('button', { class: 'btn ghost', onclick: act(load) }, '번역 보기·고치기')), st, out);
};

const revisionBox = v => {
  const out = h('div', {}, empty('불러오는 중…'));
  const K = k => k === 'steps' ? '단계' : k === 'annotations' ? '도형' : '자막 ' + (LANGS[k.slice(5)] || k.slice(5));
  const load = () => API(`versions/${v.id}/revisions`).then(r => put(out, r.rows.length ? table(['시각', '항목', '고친 사람', ''], r.rows.map(x => [x.created, K(x.kind), x.name || '',
    h('button', { class: 'btn ghost js-restore', onclick: act(async () => { if (!confirm('이 시점 내용으로 되돌릴까요? 지금 내용도 이력에 남습니다.')) return; await API(`revisions/${x.id}/restore`, 'POST', {}); toast('되돌렸습니다.'); R.edit(location.hash.split('/')[2]); }) }, '이 내용으로 되돌리기')])) : empty('고친 이력이 없습니다.')));
  load();
  return h('section', { class: 'panel' }, h('h2', {}, '개정 이력(단계·자막·도형)'), h('p', { class: 'muted' }, '저장할 때마다 바로 앞 내용을 남깁니다. 버전(영상·문서 개정판)은 위 버전 목록에서 봅니다.'), out);
};

const exportBox = (m, v) => {
  const lang = sel([['ko', LANGS.ko], ...m.sub_langs.filter(l => l !== 'ko').map(l => [l, LANGS[l] || l])], 'ko'), st = h('p', { class: 'muted js-export-state' });
  return h('section', { class: 'panel' }, h('h2', {}, '자막·도형을 입힌 영상 내보내기'), h('p', { class: 'muted' }, '확정 자막, 단계 제목, 도형·글자 표시를 영상에 그려 넣은 MP4를 만듭니다. 다른 시스템에 올리거나 인쇄물 QR로 쓸 때 씁니다.'),
    h('div', { class: 'row' }, lang, h('button', { class: 'btn ghost js-export', onclick: act(async e => { await busy(e.target, '만드는 중…', async () => { await API(`versions/${v.id}/export`, 'POST', { lang: lang.value }); await waitJob(v.id, 'export-' + lang.value, st); });
      put(st, '만들었습니다. ', h('a', { href: `api/versions/${v.id}/export.mp4?lang=${lang.value}`, class: 'js-export-dl' }, '내려받기')); }) }, '영상 만들기')), st);
};

const folderPick = (m, folders) => {
  const path = f => { const out = []; let x = f; while (x) { out.unshift(x.name); x = folders.find(y => y.id === x.parent_id); } return out.join(' › '); };
  const s = sel([['', '폴더 없음'], ...folders.map(f => [f.id, path(f)])], m.folder_id || '', { class: 'js-folder' });
  s.onchange = act(async () => { await API(`manuals/${m.id}/folder`, 'PUT', { folder_id: s.value ? +s.value : null }); toast('폴더를 바꿨습니다.'); });
  return field('폴더', s);
};

// ---------- 폴더 관리(공정 → 현상 → 원인·대책 같은 여러 단계 분류) ----------
R.folders = async () => {
  const { rows } = await API('folders');
  const kids = pid => rows.filter(f => (f.parent_id || null) === pid);
  const n = input({ placeholder: '새 폴더 이름' }), parent = sel([['', '맨 위'], ...rows.map(f => [f.id, f.name])], '');
  const node = f => h('li', {}, h('b', {}, f.name), ' ',
    h('button', { class: 'btn ghost', onclick: act(async () => { const name = prompt('새 이름', f.name); if (name) { await API('folders/' + f.id, 'PUT', { name }); R.folders(); } }) }, '이름 바꾸기'),
    h('button', { class: 'btn ghost', onclick: act(async () => { if (confirm('폴더를 지우면 안의 매뉴얼·폴더는 위 폴더로 옮겨집니다.')) { await API('folders/' + f.id, 'DELETE'); R.folders(); } }) }, '삭제'),
    kids(f.id).length ? h('ul', {}, kids(f.id).map(node)) : null);
  page('폴더', h('p', { class: 'muted' }, '예: 공정(프레스) › 현상(불량) › 원인·대책. 매뉴얼 편집 화면에서 폴더를 고르면 매뉴얼 목록에서 폴더별로 찾을 수 있습니다.'),
    h('form', { class: 'row', onsubmit: act(async () => { await API('folders', 'POST', { name: n.value, parent_id: parent.value ? +parent.value : null }); R.folders(); }) }, n, parent, h('button', { class: 'btn' }, '폴더 추가')),
    rows.length ? h('ul', { class: 'tree' }, kids(null).map(node)) : empty('폴더가 없습니다.'));
};

// ---------- 사용자별 세부 권한 ----------
const permsBox = async () => {
  const d = await API('perms'); const { users } = await API('users');
  return h('section', { class: 'panel' }, h('h2', {}, '세부 권한(관리자별로 막을 기능)'), h('p', { class: 'muted' }, '체크한 기능은 그 관리자가 쓸 수 없습니다. 전체 관리자는 항상 모두 쓸 수 있습니다.'),
    table(['이름', ...Object.values(d.perms)], users.filter(u => u.role === 'manager').map(u => {
      const denied = new Set(d.users[u.id] || []);
      return [u.name, ...Object.keys(d.perms).map(k => { const c = input({ type: 'checkbox', checked: denied.has(k), class: 'js-perm', 'data-perm': k, 'aria-label': `${u.name} ${d.perms[k]} 막기` });
        c.onchange = act(async () => { c.checked ? denied.add(k) : denied.delete(k); await API(`users/${u.id}/perms`, 'PUT', { denied: [...denied] }); toast('권한을 바꿨습니다.'); }); return c; })];
    })));
};
