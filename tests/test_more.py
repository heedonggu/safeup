"""원본 대조로 추가한 기능 확인: 이메일 가입·2단계 인증·IP 제한·백업, 문서 매뉴얼·즐겨찾기·공개 범위·작성 계획·다단 승인·리포트,
스킬 평가·자기평가·계획, AI 골자·단계 나누기·읽기 음성·음성 교체, 요소 작업 분해·차이 분석, 점검 결과 승인.  실행: py tests/test_more.py [--no-ai]"""
import http.cookiejar, io, json, os, subprocess, sys, tempfile, time, urllib.error, urllib.request
from openpyxl import load_workbook

B = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, B)
AI = '--no-ai' not in sys.argv
tmp = tempfile.mkdtemp(); port = 8895; U = f'http://127.0.0.1:{port}'
# 안전보건 웹앱 /api/edu/complete 를 흉내 내는 서버
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
EDU = []


class Safety(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        good = self.path == '/api/edu/complete' and self.headers.get('x-edu-secret') == 'edu-test'
        if good:
            EDU.append(body)
        self.send_response(200 if good else 401); self.end_headers(); self.wfile.write(b'{}')


sv = ThreadingHTTPServer(('127.0.0.1', 8894), Safety); threading.Thread(target=sv.serve_forever, daemon=True).start()
srv = subprocess.Popen([sys.executable, os.path.join(B, 'server.py')], env=dict(os.environ, PORT=str(port), DATA_DIR=tmp, ADMIN_PASSWORD='Test-pass-1', PYTHONUTF8='1',
                       SAFETY_ORIGIN='http://127.0.0.1:8894', EDU_SECRET='edu-test'), cwd=B, stdout=subprocess.DEVNULL)
n = 0
PNG = bytes.fromhex('89504e470d0a1a0a0000000d4948445200000001000000010806000000') + b'\x1f\x15\xc4\x89' + bytes.fromhex('0000000a49444154789c6300010000050001') + b'\r\n-\xb4' + bytes.fromhex('0000000049454e44ae426082')


def ok(c, m):
    global n
    n += 1
    if not c:
        print('FAIL', m); srv.kill(); sys.exit(1)


class S:
    def __init__(s):
        s.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def r(s, path, data=None, method=None, raw=None, headers=None):
        hd = dict(headers or {}); body = None
        if data is not None:
            body = json.dumps(data).encode(); hd['Content-Type'] = 'application/json'
        if raw is not None:
            body = raw; hd['Content-Type'] = 'application/octet-stream'
        try:
            with s.op.open(urllib.request.Request(U + path, body, hd, method=method), timeout=300) as x:
                return x.status, x.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def j(s, path, data=None, method=None, want=200, raw=None):
        c, b = s.r(path, data, method, raw)
        ok(c == want, f'{method or ("POST" if data is not None or raw is not None else "GET")} {path} -> {c} {b[:200]}')
        return json.loads(b) if b[:1] in (b'{', b'[') else b

    def login(s, u, p, otp=None):
        return s.j('/api/login', dict(user=u, password=p, **({'otp': otp} if otp else {})))


def wait_job(a, vid, lang, secs=600):
    for _ in range(secs):
        j = [x for x in a.j(f'/api/versions/{vid}/status')['jobs'] if x['lang'] == lang]
        if j and j[0]['state'] != 'running':
            return j[0]
        time.sleep(1)


try:
    for _ in range(50):
        try:
            urllib.request.urlopen(U + '/', timeout=1); break
        except Exception:
            time.sleep(.2)
    a = S(); a.login('admin', 'Test-pass-1')
    # 이메일 가입 → 승인 → 이메일로 로그인
    g = S()
    g.j('/api/signup', dict(name='지메일', email='bad', password='Gmail-pass-1', consent=True), want=400)
    g.j('/api/signup', dict(name='지메일', email='me@gmail.com', password='short', consent=True), want=400)
    g.j('/api/signup', dict(name='지메일', email='me@gmail.com', password='Gmail-pass-1'), want=400)
    ok(g.j('/api/signup', dict(name='지메일', email='Me@Gmail.com', password='Gmail-pass-1', consent=True, company='전주공장', dept='생산'))['pending'], 'signup')
    g.j('/api/signup', dict(name='x', email='me@gmail.com', password='Gmail-pass-1', consent=True), want=400)
    c, b = g.r('/api/login', dict(user='me@gmail.com', password='Gmail-pass-1')); ok(c == 403 and '승인' in b.decode(), 'pending login blocked')
    u = [x for x in a.j('/api/users')['users'] if x['email'] == 'me@gmail.com'][0]; ok(u['pending'] and not u['active'], 'pending listed')
    a.j(f"/api/users/{u['id']}", dict(active=True, role='admin'), 'PUT')
    g.login('ME@gmail.com', 'Gmail-pass-1'); me = g.j('/api/me')['user']; ok(me['role'] == 'admin' and not me['pending'], 'approved login by email')
    # 2단계 인증
    import more
    k = g.j('/api/me/2fa/setup', {})['key']
    g.j('/api/me/2fa/enable', dict(code='000000'), want=400)
    g.j('/api/me/2fa/enable', dict(code=more.totp(k)))
    t = S(); c, b = t.r('/api/login', dict(user='me@gmail.com', password='Gmail-pass-1')); ok(c == 401 and json.loads(b)['need_otp'], 'otp required')
    t.j('/api/login', dict(user='me@gmail.com', password='Gmail-pass-1', otp='123456'), want=401)
    t.login('me@gmail.com', 'Gmail-pass-1', more.totp(k)); ok(t.j('/api/me')['user']['totp'], 'otp login')
    g.j('/api/me/2fa/disable', dict(code=more.totp(k)))
    # IP 제한·백업
    g.j('/api/settings/security', dict(allowed_ips='10.0.0.0/8'), 'PUT', want=400)       # 내 IP가 빠지면 저장 거부
    g.j('/api/settings/security', dict(allowed_ips='nope'), 'PUT', want=400)
    g.j('/api/settings/security', dict(allowed_ips='127.0.0.1, 10.0.0.0/8'), 'PUT')
    ok(g.j('/api/settings/security')['allowed_ips'] == '127.0.0.1,10.0.0.0/8', 'ip saved')
    g.j('/api/settings/security', dict(allowed_ips=''), 'PUT')
    c, b = g.r('/api/backup', {}); ok(c == 200 and b[:15] == b'SQLite format 3', 'backup')
    # 문서 매뉴얼·그림·개정·열람 이수
    w = S(); r = g.j('/api/users', dict(users=[dict(login='w1', name='작업자', dept='생산'), dict(login='w2', name='타부서', dept='물류'), dict(login='m2', name='승인자2', role='manager')]))
    pw = {x['login']: x['password'] for x in r['created']}; ids = {x['login']: x['id'] for x in r['created']}
    for who, s_ in (('w1', w),):
        s_.login(who, pw[who]); s_.j('/api/me/password', dict(old=pw[who], new='Worker-pass-1')); s_.login(who, 'Worker-pass-1')
    w2 = S(); w2.login('w2', pw['w2']); w2.j('/api/me/password', dict(old=pw['w2'], new='Worker-pass-2')); w2.login('w2', 'Worker-pass-2')
    m2 = S(); m2.login('m2', pw['m2']); m2.j('/api/me/password', dict(old=pw['m2'], new='Manager-pass-2')); m2.login('m2', 'Manager-pass-2')
    did = g.j('/api/manuals', dict(title='점검 절차서', kind='doc', tags='점검, 신입'))['id']
    d = g.j(f'/api/manuals/{did}'); ok(d['kind'] == 'doc' and d['version']['state'] == 'ready', 'doc manual')
    g.j('/api/images', raw=b'not image', want=400)
    img = g.j('/api/images', raw=PNG)['image']
    ok(w.r(f'/api/images/{img}')[0] == 200 and S().r(f'/api/images/{img}')[0] == 401, 'image auth')
    g.j(f"/api/versions/{d['current_version']}/steps", dict(steps=[dict(title='전원 차단', note='메인 차단기를 내린다', image=img), dict(title='잠금', warn='꼬리표 부착', image='../x.png')]), 'PUT', want=400)
    g.j(f"/api/versions/{d['current_version']}/steps", dict(steps=[dict(title='전원 차단', note='메인 차단기를 내린다', image=img), dict(title='잠금', warn='꼬리표 부착')]), 'PUT')
    v2 = g.j(f'/api/manuals/{did}/docversion', dict(reason='잠금 절차 보강'))['version_id']
    d = g.j(f'/api/manuals/{did}'); ok(d['current_version'] == v2 and len(d['steps']) == 2 and d['steps'][0]['image'] == img, 'doc revision keeps steps')
    # 공개 범위·즐겨찾기
    g.j(f'/api/manuals/{did}', dict(status='published', scope='생산'), 'PUT')
    ok([m['id'] for m in w.j('/api/manuals')['manuals']] == [did] and not w2.j('/api/manuals')['manuals'], 'scope list')
    w2.j(f'/api/manuals/{did}', want=404)
    w.j(f'/api/manuals/{did}/bookmark', dict(on=True)); ok(w.j('/api/manuals')['manuals'][0]['bookmarked'], 'bookmark')
    w.j(f'/api/manuals/{did}/bookmark', dict(on=False)); ok(not w.j(f'/api/manuals/{did}')['bookmarked'], 'unbookmark')
    g.j(f'/api/manuals/{did}/assign', dict(user_ids=[ids['w2']])); ok(w2.j(f'/api/manuals/{did}')['id'] == did, 'assigned outside scope can see')
    w.j(f'/api/versions/{v2}/progress', dict(pct=100)); ok(w.j(f'/api/manuals/{did}/complete', dict(signature='data:image/png;base64,iVBORw0KGgo='))['passed'], 'doc complete')
    time.sleep(1); ok(len(EDU) == 1 and EDU[0]['course'] == '점검 절차서' and EDU[0]['worker'] == '작업자' and EDU[0]['ref'].endswith(f":{ids['w1']}"), f'edu sync {EDU}')
    ok(w.j('/api/me')['safety'], 'safety flag')
    rp = g.j(f'/api/manuals/{did}/report'); ok(rp['total'] == 1 and rp['rows'][0]['name'] == '타부서', 'report')
    # 작성 계획
    pid = g.j('/api/plans', dict(title='지게차 점검 매뉴얼', owner_id=ids['m2'], due='2026-12-01'))['id']
    g.j(f'/api/plans/{pid}', dict(status='done', manual_id=did), 'PUT'); g.j(f'/api/plans/{pid}', dict(status='zz'), 'PUT', want=400)
    ok(g.j('/api/plans')['rows'][0]['manual'] == '점검 절차서', 'plan linked')
    # 다단 승인: 관리자(me) → m2 순서
    aid = g.j('/api/manuals', dict(title='승인 대상', kind='doc'))['id']
    g.j(f'/api/manuals/{aid}/approval', dict(approver_ids=[ids['w1']]), want=400)
    g.j(f'/api/manuals/{aid}/approval', dict(approver_ids=[me['id'], ids['m2']]))
    ok(g.j(f'/api/manuals/{aid}')['status'] == 'review', 'review status')
    g.j(f'/api/manuals/{aid}', dict(status='published'), 'PUT', want=400)
    ok(not m2.j('/api/approvals')['rows'], 'not m2 turn yet')
    first = g.j('/api/approvals')['rows'][0]; m2.j(f"/api/approvals/{first['id']}", dict(ok=True), want=403)
    ok(not g.j(f"/api/approvals/{first['id']}", dict(ok=True, comment='확인'))['published'], 'step1')
    second = m2.j('/api/approvals')['rows'][0]; ok(m2.j(f"/api/approvals/{second['id']}", dict(ok=True))['published'], 'step2 publishes')
    g.j(f'/api/manuals/{aid}/approval', dict(approver_ids=[ids['m2']])); r_ = m2.j('/api/approvals')['rows'][0]
    m2.j(f"/api/approvals/{r_['id']}", dict(ok=False, comment='수정 필요')); ok(g.j(f'/api/manuals/{aid}')['status'] == 'draft', 'reject -> draft')
    # 스킬
    sid = g.j('/api/skills', dict(name='프레스 조작', category='생산', manual_ids=[did]))['id']
    g.j('/api/skills/eval', dict(user_id=ids['w1'], skill_id=sid, level=9), want=400)
    g.j('/api/skills/eval', dict(user_id=ids['w1'], skill_id=sid, level=2, comment='관찰'))
    w.j('/api/skills/self', dict(skill_id=sid, level=3)); w.j('/api/skills/eval', dict(user_id=ids['w1'], skill_id=sid, level=4), want=403)
    ok(g.j('/api/skills/plan', dict(skill_id=sid, target=3, due='2020-01-01', dept='생산'))['planned'] == 2, 'plan dept')
    mx = g.j('/api/skills/matrix'); cl = mx['cells'][f"{ids['w1']}:{sid}"]; ok(cl['level'] == 2 and cl['self'] == 3 and cl['target'] == 3 and cl['late'], f'skill cell {cl}')
    ok(len(mx['milestones']) == 2, 'milestones')
    c, b = g.r('/api/skills/matrix.xlsx'); ok(c == 200 and load_workbook(io.BytesIO(b)).active['C1'].value == '프레스 조작', 'skill xlsx')
    pv = w.j('/api/skills/me')['skills'][0]; ok(pv['education'] and len(pv['history']) == 2, 'person view')
    w.j(f"/api/skills/user/{ids['w1']}", want=403)
    # 점검 결과 승인
    fid = g.j('/api/forms', dict(title='일일', schema=[dict(label='압력', type='number', min=1, max=5)]))['id']
    sub = w.j(f'/api/forms/{fid}/submit', dict(values={'0': 3}))['id']
    g.j(f'/api/submissions/{sub}/review', dict(ok=True)); ok(g.j(f'/api/forms/{fid}/submissions')['rows'][0]['status'] == 'ok', 'submission approved')
    w.j(f'/api/submissions/{sub}/review', dict(ok=True), want=403)
    # 영상: 단계 자동 분할·읽기 음성·요소 분해·차이 분석
    video = open(os.path.join(B, 'tests/fixtures/sample.mp4'), 'rb').read()
    vm = g.j('/api/manuals', dict(title='영상 매뉴얼'))['id']
    vid = g.j(f'/api/manuals/{vm}/versions', raw=video)['version_id']
    for _ in range(240):
        if g.j(f'/api/versions/{vid}/status')['state'] != 'processing':
            break
        time.sleep(.5)
    g.j(f'/api/versions/{vid}/autosteps', {}, want=400)
    g.j(f'/api/versions/{vid}/elements', {}); ok(wait_job(g, vid, 'split')['state'] == 'done', 'split')
    el = g.j(f'/api/versions/{vid}/elements'); ok(el['rows'] and abs(el['rows'][-1]['end'] - el['duration']) < 0.2 and all(r['end'] - r['start'] <= 10.01 for r in el['rows']), f'elements {el}')
    g.j(f'/api/versions/{vid}/elements', dict(rows=[dict(start=0, end=3, label='준비'), dict(start=3, end=el['duration'], label='작업')]), 'PUT')
    if AI:
        g.j(f'/api/versions/{vid}/subs/draft', {}); ok(wait_job(g, vid, 'ko')['state'] == 'done', 'asr')
        subs = g.j(f'/api/versions/{vid}/subs?lang=ko')['subs']
        st = g.j(f'/api/versions/{vid}/autosteps', {})['steps']; ok(st and st[0]['title'] and st[-1]['end'] <= el['duration'] + .01, f'autosteps {st}')
        g.j(f'/api/versions/{vid}/tts', dict(lang='ko'), want=400)   # 확정 전
        g.j(f'/api/versions/{vid}/subs', dict(lang='ko', confirm=True, subs=subs), 'PUT')
        g.j(f'/api/versions/{vid}/tts', dict(lang='ko')); ok(wait_job(g, vid, 'tts-ko', 300)['state'] == 'done', 'tts')
        c, b = w.r(f'/api/versions/{vid}/narration?lang=ko'); ok(c == 404 or len(b) > 1000, 'narration scope')
        ok(len(g.r(f'/api/versions/{vid}/narration?lang=ko')[1]) > 1000 and 'ko' in g.j(f'/api/manuals/{vm}')['narrations'], 'narration')
        g.j(f'/api/versions/{vid}/tts', dict(lang='ko', replace=True)); ok(wait_job(g, vid, 'tts-ko', 300)['state'] == 'done', 'tts replace')
        m = g.j(f'/api/manuals/{vm}'); ok(m['current_version'] != vid and '교체' in m['versions'][0]['reason'] and len(m['versions']) == 2, 'replaced version')
        nv = m['current_version']; g.j(f'/api/versions/{nv}/elements', dict(rows=[dict(start=0, end=4, label='준비'), dict(start=4, end=m['version']['duration'], label='작업')]), 'PUT')
        ex = g.j('/api/compare/explain', dict(a=vid, b=nv)); ok(len(ex['diffs']) == 2 and ex['diffs'][0]['diff'] == 1.0 and ex['text'], f'explain {ex}')
        print('AI 설명:', ex['text'][:120])
        txt = '프레스 작업 절차\n1. 작업 전 안전모와 안전화를 착용한다.\n2. 비상정지 버튼이 작동하는지 확인한다.\n3. 금형 사이에 손을 넣지 않는다.\n4. 작업이 끝나면 전원을 차단한다.'.encode()
        ol = g.j('/api/ai/outline', raw=txt)['steps']; ok(len(ol) >= 3, f'outline {ol}')
        print('AI 골자:', [s['title'] for s in ol])
        ck = g.j('/api/ai/checklist', raw='1. 해당 작업에 적합한 보호구를 착용하였는가? 양호 미흡\n2. 안전시설물 및 단부 안전조치 상태는 양호한가? 양호 미흡\n3. 자재 및 폐기물 정리정돈 상태는 양호한가?'.encode())['items']
        ok(len(ck) >= 2 and all(i['type'] in ('check', 'number', 'text') for i in ck), f'checklist import {ck}')
    g.j('/api/ai/outline', raw=b'abc', want=400)
    # 도형 표시
    cur = g.j(f'/api/manuals/{vm}')['current_version']
    g.j(f'/api/versions/{cur}/annotations', dict(rows=[dict(start=0, end=2, kind='star', x=.1, y=.1, w=.2, h=.2)]), 'PUT', want=400)
    g.j(f'/api/versions/{cur}/annotations', dict(rows=[dict(start=0, end=2, kind='circle', x=.1, y=.1, w=.2, h=.2, color='#ff0000'), dict(start=1, end=3, kind='text', x=.5, y=.5, w=0, h=0, text='여기 확인')]), 'PUT')
    ok(len(g.j(f'/api/versions/{cur}/annotations')['rows']) == 2, 'annotations')
    # 영상 내려받기
    c, b = g.r(f'/api/versions/{cur}/download'); ok(c == 200 and len(b) > 10000, 'download'); ok(w.r(f'/api/versions/{cur}/download')[0] == 403, 'download manager only')
    # 기한 알림
    g.j(f'/api/manuals/{vm}', dict(status='published'), 'PUT')
    import datetime
    g.j(f'/api/manuals/{vm}/assign', dict(user_ids=[ids['w1']], due=(datetime.date.today() + datetime.timedelta(days=1)).isoformat()))
    nt = w.j('/api/notices')['rows']; ok(nt and nt[0]['left'] == 1 and nt[0]['title'] == '영상 매뉴얼', f'notices {nt}')
    # 활용 현황
    us = g.j('/api/usage'); ok(any(m['title'] == '점검 절차서' and m['completions'] == 1 for m in us['manuals']) and us['logins'], 'usage')
    # 설명 음성 녹음 덮어쓰기
    wav = os.path.join(tmp, 'vo.wav')
    subprocess.run(['ffmpeg', '-y', '-v', 'error', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=3', wav], check=True)
    r = g.j(f'/api/versions/{cur}/voiceover', raw=open(wav, 'rb').read()); m = g.j(f'/api/manuals/{vm}')
    ok(m['current_version'] == r['version_id'] and m['versions'][0]['reason'] == '설명 음성 녹음으로 교체' and len(g.j(f"/api/versions/{r['version_id']}/annotations")['rows']) == 2, 'voiceover version')
    g.j(f'/api/versions/{cur}/voiceover', raw=b'garbage', want=400)
    if AI:
        ok(wait_job(g, r['version_id'], 'ko')['state'] in ('done', 'failed'), 'voiceover asr ran')
    print(f'PASS {n} checks')
finally:
    srv.kill(); sv.shutdown()
