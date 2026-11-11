// 공통 동작: 메뉴, 탭, 아코디언, 필터+페이지 나누기, 모달, 쿠키 안내, 폼 제출, 관리자 화면
(() => {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const ROOT = document.body.dataset.root || '';
  const api = (p, o = {}) => fetch(ROOT + 'api/' + p, { credentials: 'same-origin', ...o });
  const post = (p, data) => api(p, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });

  // 모바일 메뉴 / 드롭다운
  const burger = $('.js-burger'), gnav = $('.js-gnav');
  burger?.addEventListener('click', () => burger.setAttribute('aria-expanded', gnav.classList.toggle('open')));
  $$('.js-dd').forEach(b => b.addEventListener('click', e => {
    e.stopPropagation();
    const li = b.parentElement, open = !li.classList.contains('open');
    $$('.dd.open').forEach(x => x.classList.remove('open'));
    li.classList.toggle('open', open); b.setAttribute('aria-expanded', open);
  }));
  document.addEventListener('click', () => $$('.dd.open').forEach(x => x.classList.remove('open')));
  document.addEventListener('keydown', e => { if (e.key === 'Escape') { $$('.dd.open').forEach(x => x.classList.remove('open')); closeModal(); } });

  // 탭
  const tabs = (btnSel, panSel) => $$(btnSel).forEach(b => b.addEventListener('click', () => {
    $$(btnSel).forEach(x => x.classList.toggle('is-active', x === b));
    $$(panSel).forEach(p => p.classList.toggle('is-active', p.dataset.panelId === b.dataset.targetPanel));
  }));
  tabs('.js-industry-tab-button', '.js-industry-tab-panel');
  tabs('.js-case-logo-tab-button', '.js-case-logo-tab-panel');

  // 아코디언: 하나만 열림
  $$('.js-acc').forEach(d => d.addEventListener('toggle', () => { if (d.open) $$('.js-acc').forEach(o => o !== d && (o.open = false)); }));

  // 화면에 들어오면 재생되는 영상
  const vids = $$('video.js-autoplay-video');
  if (vids.length && 'IntersectionObserver' in window) {
    const io = new IntersectionObserver(es => es.forEach(e => e.isIntersecting ? e.target.play().catch(() => {}) : e.target.pause()), { threshold: .3 });
    vids.forEach(v => { v.muted = true; io.observe(v); });
  }

  // 필터(그룹 안 OR, 그룹 간 AND) + 페이지 나누기(?page=N)
  const list = $('.js-case-list');
  const items = list ? $$('.js-case-item') : $$('.js-wp-item');
  if (items.length) {
    const PER = list ? 6 : 1e9;
    const groups = list
      ? [['.js-filter-industry', 'industry'], ['.js-filter-number', 'size'], ['.js-filter-theme', 'theme']]
      : [['.js-filter-type', 'type'], ['.js-filter-wp-industry', 'industry'], ['.js-filter-wp-theme', 'theme']];
    const pagEl = $('.js-pagination'), empty = $('.js-empty-state');
    let page = Math.max(1, parseInt(new URLSearchParams(location.search).get('page')) || 1);
    const matched = () => items.filter(it => groups.every(([s, k]) => {
      const on = $$(s + ':checked').map(c => c.value);
      return !on.length || on.includes(it.dataset[k]);
    }));
    const render = () => {
      const m = matched(), pages = Math.max(1, Math.ceil(m.length / PER));
      page = Math.min(page, pages);
      items.forEach(it => { it.hidden = true; });
      m.slice((page - 1) * PER, page * PER).forEach(it => { it.hidden = false; });
      if (empty) empty.hidden = m.length > 0;
      $$('.js-wp-section').forEach(s => { s.hidden = !$$('.js-wp-item', s).some(i => !i.hidden); });
      if (!pagEl) return;
      const ul = $('.js-pagination-list', pagEl); ul.innerHTML = '';
      if (pages < 2) return;
      const btn = (t, p, dis, cur) => {
        const li = document.createElement('li'), b = document.createElement('button');
        b.textContent = t; b.disabled = !!dis; if (cur) b.setAttribute('aria-current', 'page');
        b.addEventListener('click', () => go(p)); li.append(b); ul.append(li);
      };
      btn('‹', page - 1, page === 1);
      for (let i = 1; i <= pages; i++) btn(i, i, false, i === page);
      btn('›', page + 1, page === pages);
    };
    const go = p => {
      page = p; const u = new URL(location); p === 1 ? u.searchParams.delete('page') : u.searchParams.set('page', p);
      history.pushState(null, '', u); render(); (list || document.body).scrollIntoView({ behavior: 'smooth', block: 'start' });
    };
    groups.forEach(([s]) => $$(s).forEach(c => c.addEventListener('change', () => { page = 1; const u = new URL(location); u.searchParams.delete('page'); history.replaceState(null, '', u); render(); })));
    $('.js-filter-reset-button')?.addEventListener('click', () => { groups.forEach(([s]) => $$(s).forEach(c => (c.checked = false))); page = 1; render(); });
    addEventListener('popstate', () => { page = Math.max(1, parseInt(new URLSearchParams(location.search).get('page')) || 1); render(); });
    render();
  }

  // 기능 모달
  const modal = $('.js-skp-modal');
  const closeModal = () => { if (modal && !modal.hidden) { modal.hidden = true; lastOpener?.focus(); } };
  let lastOpener;
  $$('.js-skp-function-modal-open').forEach(b => b.addEventListener('click', () => { lastOpener = b; modal.hidden = false; $('.close', modal).focus(); }));
  $$('.js-skp-function-modal-close').forEach(b => b.addEventListener('click', closeModal));
  modal?.addEventListener('click', e => { if (e.target === modal) closeModal(); });

  // 쿠키 안내: 동의 여부만 이 브라우저에 저장
  const ck = $('.js-cookie');
  try { if (ck && !localStorage.getItem('cookie-ok')) ck.hidden = false; } catch { if (ck) ck.hidden = false; }
  $('.js-cookie-ok')?.addEventListener('click', () => { ck.hidden = true; try { localStorage.setItem('cookie-ok', '1'); } catch {} });

  // 소셜 로그인 버튼(설정된 것만) + 돌아온 오류 문구
  const social = $('.js-social');
  if (social) {
    const err = new URLSearchParams(location.search).get('err');
    if (err) { const m = $('.js-login-form .js-form-msg'); m.textContent = err; }
    fetch(ROOT + 'api/auth/providers').then(r => r.json()).then(({ providers }) => providers.forEach(p => {
      const a = document.createElement('a'); a.className = 'sbtn sbtn-' + p.id; a.href = ROOT + 'auth/' + p.id + '/start';
      a.textContent = p.label + '로 로그인'; social.append(a);
    })).catch(() => {});
  }

  // 폼 검증 + 제출
  const MSG = { req: '필수 항목을 입력하세요.', email: '이메일 형식이 올바르지 않습니다.', phone: '전화번호 형식이 올바르지 않습니다.' };
  const fieldErr = (el) => {
    const v = el.type === 'checkbox' ? el.checked : el.value.trim();
    if (el.required && !v) return MSG.req;
    if (el.type === 'email' && v && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v)) return MSG.email;
    if (el.type === 'tel' && v && !/^[0-9+()\-\s]{7,20}$/.test(v)) return MSG.phone;
    return '';
  };
  const show = (el, m) => {
    const w = el.closest('.fld'); w.classList.toggle('err', !!m); $('.e', w)?.remove();
    if (m) { const p = document.createElement('p'); p.className = 'e'; p.textContent = m; w.append(p); }
  };
  $$('.js-lead-form, .js-login-form, .js-signup-form').forEach(f => {
    $$('input,select,textarea', f).forEach(el => {
      if (el.type === 'email' || el.type === 'tel') el.addEventListener('blur', () => show(el, fieldErr(el)));
      el.addEventListener('change', () => el.closest('.fld')?.classList.contains('err') && show(el, fieldErr(el)));
    });
    f.addEventListener('submit', async e => {
      e.preventDefault();
      const msg = $('.js-form-msg', f), btn = $('button[type=submit]', f);
      let bad = 0; $$('input,select,textarea', f).forEach(el => { if (el.type === 'hidden' || el.closest('[hidden]')) return; const m = fieldErr(el); show(el, m); if (m) bad++; });
      const pw = $('input[name=password]', f);
      if (!bad && f.classList.contains('js-signup-form') && pw.value.length < 8) { show(pw, '8자 이상 입력하세요.'); bad++; }
      if (bad) { msg.className = 'msg js-form-msg'; msg.textContent = '필수 항목을 모두 입력하세요.'; return; }
      const data = Object.fromEntries(new FormData(f)); btn.disabled = true; msg.textContent = '';
      try {
        const login = f.classList.contains('js-login-form'), signup = f.classList.contains('js-signup-form');
        const r = login ? await post('login', data) : signup ? await post('signup', data) : await post('lead', { kind: f.dataset.kind, ...data });
        const j = await r.json().catch(() => ({}));
        if (j.need_otp) { const o = $('.js-otp', f); o.hidden = false; $('input', o).focus(); }
        if (!r.ok) throw new Error(j.error || '처리하지 못했습니다. 잠시 뒤 다시 시도하세요.');
        if (signup) { f.reset(); msg.className = 'msg ok js-form-msg'; msg.textContent = '가입 신청이 접수되었습니다. 관리자 승인 후 로그인할 수 있습니다.'; btn.disabled = false; return; }
        if (login) return (location.href = ROOT + 'app.html');
        if (f.dataset.next) return (location.href = ROOT + 'files/guide.pdf');
        if (f.dataset.kind === 'download') return (location.href = ROOT + 'thanks.html');
        f.reset(); msg.className = 'msg ok js-form-msg'; msg.textContent = '접수되었습니다. 확인 후 연락드리겠습니다.';
      } catch (err) { msg.className = 'msg js-form-msg'; msg.textContent = err.message; }
      btn.disabled = false;
    });
  });

})();
