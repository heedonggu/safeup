"""data.py -> site/*.html 과 private/guide.pdf 생성.  실행: PYTHONUTF8=1 py build.py
모든 링크는 상대경로라 다른 웹앱의 하위 경로(/video/ 등)에 그대로 올릴 수 있다."""
import os, shutil
from html import escape as e
from data import *

OUT = 'site'
STATIC = 'static'
FOOT_LINKS = [('faq.html', '자주 묻는 질문'), ('solution/index.html', '영상 매뉴얼이란'), ('solution/scene.html', '활용 사례'),
              ('solution/creation.html', '영상 제작 절차'), ('solution/wp.html', '자료 모음'), ('skp.html', '현장 점검표'),
              ('agency.html', '대행사 문의'), ('terms.html', '이용 약관'), ('privacy.html', '개인정보 처리방침')]


def nav(r):
    feat = ''.join(f'<li><a href="{r}feature/{s}.html">{t}</a></li>' for s, t, *_ in FEATURES)
    sc = f'<li><a href="{r}scene/index.html">활용 사례 목록</a></li>' + ''.join(f'<li><a href="{r}scene/{s}.html">{t}</a></li>' for s, t, _ in SCENES)
    return f'''<header class="hd"><div class="wrap hd-in">
<a class="logo" href="{r}index.html">{e(BRAND)}</a>
<button class="burger js-burger" aria-label="메뉴" aria-expanded="false"><span></span><span></span><span></span></button>
<nav class="gnav js-gnav" aria-label="주 메뉴"><ul>
<li><a href="{r}index.html#about">{e(BRAND)}란</a></li>
<li class="dd"><button class="js-dd" aria-expanded="false">기능</button><ul>{feat}</ul></li>
<li class="dd"><button class="js-dd" aria-expanded="false">활용 사례</button><ul>{sc}</ul></li>
<li><a href="{r}industry/{INDUSTRY[0]}.html">{INDUSTRY[1]}</a></li>
<li><a href="{r}security.html">보안</a></li>
<li><a href="{r}pricing.html">계약 플랜</a></li>
<li><a href="{r}case/index.html">도입 사례</a></li>
<li><a href="{r}event.html">이벤트</a></li>
</ul><div class="hd-cta"><a href="{r}login.html">로그인</a><a href="{r}contact.html">문의하기</a><a class="btn" href="{r}download.html">자료 청구</a></div></nav></div></header>'''


def foot(r):
    links = ''.join(f'<li><a href="{r}{h}">{t}</a></li>' for h, t in FOOT_LINKS)
    return f'<footer class="ft"><div class="wrap"><ul>{links}</ul><p>© {e(COMPANY)} · {e(BRAND)}</p></div></footer>'


COOKIE = '''<div class="cookie js-cookie" hidden><p>이 사이트는 서비스 동작에 필요한 쿠키만 사용합니다. 광고·분석 추적은 하지 않습니다.</p>
<button class="btn js-cookie-ok">확인</button></div>'''


def page(path, title, body, desc=''):
    depth = path.count('/')
    r = '../' * depth
    html = f'''<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{e(title)} | {e(BRAND)}</title>
<meta name="description" content="{e(desc or SLOGAN)}"><link rel="stylesheet" href="{r}assets/style.css"></head>
<body data-root="{r}">{nav(r)}<main>{body}</main>{foot(r)}{COOKIE}<script src="{r}assets/app.js"></script></body></html>'''
    p = os.path.join(OUT, path)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, 'w', encoding='utf8').write(html)


def hero(h, lead, ctas=True, r=''):
    c = f'<p class="ctas"><a class="btn" href="{r}download.html">자료 청구</a> <a class="btn ghost" href="{r}contact.html">문의하기</a></p>' if ctas else ''
    return f'<section class="hero"><div class="wrap"><h1>{e(h)}</h1><p class="lead">{e(lead)}</p>{c}</div></section>'


def sections(secs):
    out = ''
    for h, p, bl in secs:
        li = ''.join(f'<li>{e(b)}</li>' for b in bl)
        out += f'<section class="sec"><div class="wrap"><h2>{e(h)}</h2><p>{e(p)}</p><ul class="ticks">{li}</ul></div></section>'
    return out


def cta(r):
    return f'<section class="sec cta"><div class="wrap"><h2>도입 상담과 자료 청구</h2><p class="ctas"><a class="btn" href="{r}download.html">자료 청구</a> <a class="btn ghost" href="{r}contact.html">문의하기</a></p></div></section>'


def faq_html(items):
    return '<div class="faq">' + ''.join(f'<details class="js-acc"><summary>{e(q)}</summary><p>{e(a)}</p></details>' for q, a in items) + '</div>'


def case_card(c, r):
    cid, t, ind, sz, th = c
    return (f'<li class="card js-case-item js-pagination-contents-item" data-industry="{ind}" data-size="{sz}" data-theme="{th}">'
            f'<a href="{r}case/{cid}.html"><span class="tags"><b>{INDUSTRIES[ind]}</b><b>{SIZES[sz]}</b><b>{THEMES[th]}</b></span><strong>{e(t)}</strong></a></li>')


def checks(cls, label, opts):
    return (f'<fieldset class="flt"><legend>{label}</legend>' +
            ''.join(f'<label><input type="checkbox" class="{cls}" value="{k}"> {v}</label>' for k, v in opts.items()) + '</fieldset>')


PAG = '<nav class="pag js-pagination" aria-label="페이지"><ul class="js-pagination-list"></ul></nav>'
EMPTY = '<p class="empty js-empty-state" hidden>조건에 맞는 항목이 없습니다.</p>'
RESET = '<button type="button" class="btn ghost js-filter-reset-button">조건 초기화</button>'


def field(name, label, kind='text', req=True, extra=''):
    return (f'<div class="fld"><label for="f-{name}">{label}{" <i>*</i>" if req else ""}</label>'
            f'<input id="f-{name}" name="{name}" type="{kind}" {"required" if req else ""} {extra}></div>')


def select(name, label, opts, req=True):
    o = '<option value="">선택하세요</option>' + ''.join(f'<option>{e(x)}</option>' for x in opts)
    return f'<div class="fld"><label for="f-{name}">{label}{" <i>*</i>" if req else ""}</label><select id="f-{name}" name="{name}" {"required" if req else ""}>{o}</select></div>'


EMP = ['50명 미만', '50~300명', '300~1,000명', '1,000명 이상']
CONSENT = ('<div class="fld chk"><label><input type="checkbox" name="consent" required> '
           '<a href="{r}privacy.html" target="_blank">개인정보 처리방침</a>에 동의합니다. <i>*</i></label></div>')


def form(kind, fields, btn, r):
    return (f'<form class="form js-lead-form" data-kind="{kind}" novalidate>{fields}{CONSENT.format(r=r)}'
            f'<p class="msg js-form-msg" role="alert"></p><button class="btn wide" type="submit">{btn}</button></form>')


def build():
    shutil.rmtree(OUT, ignore_errors=True)
    shutil.copytree(STATIC, os.path.join(OUT, 'assets'))
    shutil.copy(os.path.join(STATIC, 'sw.js'), os.path.join(OUT, 'sw.js'))  # 서비스 워커는 앱과 같은 경로에 있어야 한다
    # 홈
    r = ''
    feats = ''.join(f'<li class="card"><a href="feature/{s}.html"><strong>{t}</strong><span>{d}</span></a></li>' for s, t, d, _ in FEATURES)
    tabs = ''.join(f'<button class="js-industry-tab-button{" is-active" if i == 0 else ""}" data-target-panel="{k}">{v}</button>' for i, (k, v) in enumerate(INDUSTRIES.items()))
    USE = {'build': ['골조·거푸집 작업 순서', '비계 설치·해체 전 교육', '마감 공종 품질 기준'], 'civil': ['굴착·흙막이 작업 전 교육', '건설기계 신호수 교육', '교량·도로 점검 절차'],
           'mep': ['전기 작업 잠금·표지 절차', '배관 용접 화기 작업 교육', '설비 시운전 점검'], 'interior': ['고소 작업대 사용 교육', '분진·소음 보호구 착용', '마감재 시공 표준']}
    panels = ''.join(
        f'<div class="js-industry-tab-panel tabpanel{" is-active" if i == 0 else ""}" data-panel-id="{k}"><ul class="ticks">' +
        ''.join(f'<li>{e(x)}</li>' for x in USE[k]) + '</ul></div>'
        for i, k in enumerate(INDUSTRIES))
    body = (hero(SLOGAN, '작업 영상을 매뉴얼로 만들고, 누가 교육을 이수했는지 기록합니다.') +
            f'<section class="sec" id="about"><div class="wrap"><h2>{e(BRAND)}란</h2><p>현장 작업 영상을 단계별 매뉴얼로 만들고, 작업자별 교육 이수 기록을 남기는 서비스입니다. 중대재해처벌법 대응에 필요한 안전보건 교육 기록을 한곳에 모읍니다.</p></div></section>'
            f'<section class="sec"><div class="wrap"><h2>주요 기능</h2><ul class="grid">{feats}</ul></div></section>'
            f'<section class="sec"><div class="wrap"><h2>공종별 활용</h2><div class="tabs">{tabs}</div>{panels}</div></section>'
            f'<section class="sec"><div class="wrap"><h2>자주 묻는 질문</h2>{faq_html(FAQ[:4])}<p><a href="faq.html">FAQ 더 보기 →</a></p></div></section>' + cta(r))
    page('index.html', SLOGAN, body)
    # 기능
    for s, t, d, secs in FEATURES:
        page(f'feature/{s}.html', t, hero(t, d, r='../') + sections(secs) + cta('../'), d)
    # 활용 사례
    sc = ''.join(f'<li class="card"><a href="{s}.html"><strong>{t}</strong><span>{d}</span></a></li>' for s, t, d in SCENES)
    page('scene/index.html', '활용 사례 목록', hero('활용 사례 목록', '목적별로 어떻게 쓰는지 모았습니다.', r='../') + f'<section class="sec"><div class="wrap"><ul class="grid">{sc}</ul></div></section>' + cta('../'))
    for s, t, d in SCENES:
        page(f'scene/{s}.html', t, hero(t, d, r='../') + sections(SCENE_BODY[s]) + cta('../'), d)
    # 업종별
    s, t, d, secs = INDUSTRY
    page(f'industry/{s}.html', t, hero(t, d, r='../') + sections(secs) + cta('../'), d)
    # 보안
    sec = ''.join(f'<li class="card"><strong>{e(a)}</strong><span>{e(b)}</span></li>' for a, b in SECURITY)
    page('security.html', '보안', hero('보안', '영상과 교육 기록을 안전하게 다루는 방법입니다.') + f'<section class="sec"><div class="wrap"><ul class="grid">{sec}</ul></div></section>' + cta(''))
    # 요금
    pl = ''.join(f'<li class="card"><strong>{e(n)}</strong><span>{e(w)}</span><ul class="ticks">' + ''.join(f'<li>{e(x)}</li>' for x in f) + '</ul><b>가격 문의</b></li>' for n, w, f in PLANS)
    page('pricing.html', '계약 플랜', hero('계약 플랜', '사용 인원과 기능 구성에 따라 견적을 드립니다.') + f'<section class="sec"><div class="wrap"><ul class="grid">{pl}</ul></div></section>' + cta(''))
    # 도입 사례 목록 + 상세
    filt = checks('js-filter-industry', '업종', INDUSTRIES) + checks('js-filter-number', '규모', SIZES) + checks('js-filter-theme', '목적', THEMES)
    cards = ''.join(case_card(c, '') for c in CASES)
    page('case/index.html', '도입 사례', hero('도입 사례', '현재 공개된 도입 사례가 없습니다. 사례가 생기면 이곳에 올립니다.', False, '../') +
         (f'<section class="sec"><div class="wrap"><div class="flts">{filt}{RESET}</div>{EMPTY}<ul class="grid js-pagination-contents-list js-case-list">{cards}</ul>{PAG}</div></section>'.replace('href="case/', 'href="') if CASES
          else '<section class="sec"><div class="wrap"><p class="empty">아직 공개된 도입 사례가 없습니다. <a href="../contact.html">문의하기</a>로 시연을 요청할 수 있습니다.</p></div></section>'))
    for cid, t, ind, sz, th in CASES:
        b = (hero(t, f'{INDUSTRIES[ind]} · {SIZES[sz]} · {THEMES[th]}', False, '../') +
             f'<section class="sec"><div class="wrap"><p>이 페이지는 사례 양식 샘플입니다. 과제, 도입 과정, 결과를 실제 내용으로 채웁니다.</p><p><a href="index.html">← 목록으로</a></p></div></section>' + cta('../'))
        page(f'case/{cid}.html', t, b)
    # 문의
    ct = form('contact', field('company', '회사명') + field('name', '이름') + field('email', '이메일', 'email') + field('phone', '전화번호', 'tel', False) +
              select('category', '문의 종류', ['도입 상담', '시연 신청', '견적 요청', '기타']) +
              '<div class="fld"><label for="f-message">문의 내용 <i>*</i></label><textarea id="f-message" name="message" rows="5" required></textarea></div>', '문의 보내기', '')
    page('contact.html', '문의하기', hero('문의하기', '도입 상담, 시연, 견적 요청을 받습니다.', False) + f'<section class="sec"><div class="wrap narrow">{ct}</div></section>')
    # 자료 청구 / 감사
    dl = form('download', field('company', '회사명') + field('name', '이름') + field('email', '이메일', 'email') + field('phone', '전화번호', 'tel') +
              select('employees', '직원 수', EMP) + select('role', '직책', ['경영진', '안전보건 담당', '교육 담당', '현장 관리자', '기타']) +
              '<input type="hidden" name="doc" value="서비스 소개서">', '소개서 받기', '')
    page('download.html', '자료 청구', hero('서비스 소개서 다운로드', '양식을 제출하면 바로 내려받을 수 있습니다.', False) + f'<section class="sec"><div class="wrap narrow">{dl}</div></section>')
    sv = (f'<form class="form js-lead-form" data-kind="survey" data-next="__PDF__" novalidate>' +
          select('task', '가장 해결하고 싶은 과제', ['안전교육 기록 관리', '신입 교육 표준화', '기술 전수', '품질 편차 줄이기', '기타'], True) +
          '<p class="msg js-form-msg" role="alert"></p><button class="btn wide" type="submit">설문 제출하고 소개서 받기</button></form>')
    page('thanks.html', '제출 완료', hero('제출이 완료되었습니다', '설문에 답하시면 소개서를 내려받을 수 있습니다.', False) +
         f'<section class="sec"><div class="wrap narrow">{sv}<p><a class="js-pdf-link" href="files/guide.pdf">설문 없이 바로 받기</a></p></div></section>')
    # 이벤트
    ev = ''.join(f'<li class="card"><strong>{e(t)}</strong><span>{d} · {w}</span><a class="btn ghost" href="contact.html">참가 문의</a></li>' for d, t, w in EVENTS)
    page('event.html', '이벤트', hero('이벤트·세미나', '예정된 행사가 없습니다. 일정이 정해지면 이곳에 올립니다.', False) + f'<section class="sec"><div class="wrap">{'<ul class=grid>' + ev + '</ul>' if ev else '<p class=empty>예정된 행사가 없습니다. <a href=contact.html>문의하기</a>로 시연을 요청할 수 있습니다.</p>'}</div></section>')
    # FAQ / 솔루션
    page('faq.html', '자주 묻는 질문', hero('자주 묻는 질문', '', False) + f'<section class="sec"><div class="wrap">{faq_html(FAQ)}</div></section>' + cta(''))
    page('solution/index.html', '영상 매뉴얼이란', hero('영상 매뉴얼이란', '글과 사진 대신 영상으로 작업 방법을 전달하는 방식입니다.', False, '../') +
         sections([('왜 영상인가', '순서와 손 동작은 글로 설명하기 어렵습니다. 영상은 같은 내용을 같은 방식으로 전달합니다.', ['설명 시간 단축', '교육자에 따른 편차 감소', '반복 시청 가능'])]) + cta('../'))
    page('solution/scene.html', '영상 활용 사례', hero('영상 활용 사례', '', False, '../') +
         f'<section class="sec"><div class="wrap"><ul class="grid">{"".join(f"<li class=card><a href=../scene/{s}.html><strong>{t}</strong><span>{d}</span></a></li>" for s, t, d in SCENES)}</ul></div></section>' + cta('../'))
    steps = [('촬영', '스마트폰으로 작업을 찍습니다.', ['한 작업 한 영상', '손 위치가 보이게']), ('편집', '단계로 나누고 제목을 붙입니다.', ['구간 지정', '자막 추가']),
             ('배포', '대상 작업자에게 공개합니다.', ['부서별 공개', '시청 확인']), ('개정', '방법이 바뀌면 새 버전을 올립니다.', ['버전 이력', '개정 사유'])]
    page('solution/creation.html', '영상 제작 절차', hero('영상 제작 절차', '촬영부터 개정까지 네 단계입니다.', False, '../') + sections(steps) + cta('../'))
    # 자료 모음 (필터 + 구간별 목록 + 페이지)
    wf = checks('js-filter-type', '자료 종류', RES_TYPES) + checks('js-filter-wp-industry', '업종', INDUSTRIES) + checks('js-filter-wp-theme', '목적', THEMES)
    secs = ''
    for k, kn in RES_TYPES.items():
        its = ''.join(f'<li class="card js-wp-item" data-type="{k}" data-industry="{i}" data-theme="{th}"><strong>{e(t)}</strong><a class="btn ghost" href="../download.html">받기</a></li>'
                      for t, ty, i, th in RESOURCES if ty == k)
        secs += f'<div class="js-wp-section"><h2>{kn}</h2><ul class="grid">{its}</ul></div>'
    page('solution/wp.html', '자료 모음', hero('자료 모음', '서비스 소개서는 자료 청구에서 받을 수 있습니다. 다른 자료는 준비되면 올립니다.', False, '../') +
         (f'<section class="sec"><div class="wrap"><div class="flts">{wf}{RESET}</div>{EMPTY}{secs}</div></section>' if RESOURCES
          else '<section class="sec"><div class="wrap"><p class="empty">공개 자료를 준비하고 있습니다. <a href="../download.html">서비스 소개서 받기</a></p></div></section>'))
    # 약관/방침/대행사
    page('terms.html', '이용 약관', hero('이용 약관', '', False) + '<section class="sec"><div class="wrap"><p>서비스 제공자와 이용자의 권리·의무를 정하는 자리입니다. 법무 검토를 거친 실제 약관으로 교체해야 합니다.</p></div></section>')
    page('privacy.html', '개인정보 처리방침', hero('개인정보 처리방침', '', False) +
         '<section class="sec"><div class="wrap"><p>수집 항목: 회사명, 이름, 이메일, 전화번호, 문의 내용. 이용 목적: 문의 응답과 자료 발송. 보관은 목적 달성 시까지입니다. 실제 방침으로 교체해야 합니다.</p></div></section>')
    page('agency.html', '대행사 문의', hero('대행사 문의', '판매·도입 대행 제휴를 받습니다.', False) + f'<section class="sec"><div class="wrap narrow">{form("agency", field("company", "회사명") + field("name", "이름") + field("email", "이메일", "email") + "<div class=fld><label for=f-message>제휴 내용 <i>*</i></label><textarea id=f-message name=message rows=5 required></textarea></div>", "제휴 문의 보내기", "")}</div></section>')
    # 현장 점검표: 탭 + 기능 모달 + FAQ
    tabs = [('digital', '디지털 점검표', '종이 점검표를 화면 입력으로 바꿉니다.'), ('alert', '이상 알림', '기준을 벗어나면 담당자에게 알립니다.'), ('report', '기록 출력', '기간별 점검 기록을 한 번에 출력합니다.')]
    tb = ''.join(f'<button class="js-case-logo-tab-button{" is-active" if i == 0 else ""}" data-target-panel="{k}">{t}</button>' for i, (k, t, _) in enumerate(tabs))
    tp = ''.join(f'<div class="js-case-logo-tab-panel tabpanel{" is-active" if i == 0 else ""}" data-panel-id="{k}"><p>{d}</p><button class="btn ghost js-skp-function-modal-open">기능 자세히 보기</button></div>' for i, (k, t, d) in enumerate(tabs))
    modal = ('<div class="modal js-skp-modal" hidden role="dialog" aria-modal="true" aria-label="기능 목록"><div class="modal-in"><button class="js-skp-function-modal-close close" aria-label="닫기">×</button>'
             '<h2>점검표 기능</h2><ul class="ticks"><li>점검 항목 양식 만들기</li><li>모바일 입력</li><li>이상 값 표시</li><li>기간별 출력</li></ul></div></div>')
    page('skp.html', '현장 점검표', hero('현장 점검표', '점검 기록을 종이에서 화면으로 옮깁니다.') + f'<section class="sec"><div class="wrap"><div class="tabs">{tb}</div>{tp}</div></section>'
         f'<section class="sec"><div class="wrap"><h2>자주 묻는 질문</h2>{faq_html(FAQ[:3])}</div></section>{modal}' + cta(''))
    # 로그인 / 관리자
    page('login.html', '로그인', hero('로그인', '계정으로 서비스에 들어갑니다.', False) +
         '<section class="sec"><div class="wrap narrow"><form class="form js-login-form" novalidate>' + field('user', '아이디') + field('password', '비밀번호', 'password') +
         '<div class="fld js-otp" hidden><label for="f-otp">인증 코드</label><input id="f-otp" name="otp" inputmode="numeric" autocomplete="one-time-code"></div>'
         '<p class="msg js-form-msg" role="alert"></p><button class="btn wide" type="submit">로그인</button></form><div class="social js-social"></div>'
         '<p class="center">계정이 없으면 <a href="signup.html">이메일로 가입 신청</a></p></div></section>')
    page('signup.html', '가입 신청', hero('이메일로 가입 신청', '관리자가 승인하면 로그인할 수 있습니다.', False) +
         '<section class="sec"><div class="wrap narrow"><form class="form js-signup-form" novalidate>' + field('name', '이름') + field('email', '이메일', 'email') +
         field('password', '비밀번호 (8자 이상)', 'password', True, 'minlength="8" autocomplete="new-password"') + field('company', '회사·사업장', 'text', False) + field('dept', '부서', 'text', False) +
         CONSENT.format(r='') + '<p class="msg js-form-msg" role="alert"></p><button class="btn wide" type="submit">가입 신청</button></form>'
         '<p class="center">이미 계정이 있으면 <a href="login.html">로그인</a></p></div></section>')
    os.makedirs(OUT, exist_ok=True)
    open(os.path.join(OUT, 'app.html'), 'w', encoding='utf8').write(f'''<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{e(BRAND)}</title><link rel="stylesheet" href="assets/style.css"></head>
<body class="app"><nav id="appnav" aria-label="서비스 메뉴"></nav><main class="appmain" id="view"></main><script src="assets/product.js"></script><script src="assets/extra.js"></script></body></html>''')
    pdf()
    print('pages', sum(len(f) for _, _, f in os.walk(OUT)) , 'files in', OUT)


def pdf():
    from reportlab.pdfgen import canvas
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    pdfmetrics.registerFont(TTFont('K', next(f for f in ('C:/Windows/Fonts/malgun.ttf', '/usr/share/fonts/truetype/nanum/NanumGothic.ttf') if os.path.exists(f))))
    os.makedirs('private', exist_ok=True)
    c = canvas.Canvas('private/guide.pdf')
    y = 800
    def line(t, size=11, dy=20):
        nonlocal y
        c.setFont('K', size); c.drawString(56, y, t); y -= dy
    line(f'{BRAND} 서비스 소개서', 22, 36); line(SLOGAN, 12, 30)
    for s, t, d, secs in FEATURES:
        line(t, 14, 22); line(d, 10, 18)
        for h, p, bl in secs:
            for b in bl: line('· ' + b, 10, 16)
        y -= 8
    line('문의: 사이트의 문의하기 페이지를 이용해 주세요.', 10)
    c.save()


if __name__ == '__main__':
    build()
