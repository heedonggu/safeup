"""서비스 전 기능을 실서버로 확인한다(영상 변환·받아쓰기·번역 포함).  실행: py tests/test_product.py [--no-ai]"""
import http.cookiejar, io, json, os, subprocess, sys, tempfile, time, urllib.error, urllib.request
from urllib.parse import quote
from openpyxl import load_workbook

B = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AI = '--no-ai' not in sys.argv
tmp = tempfile.mkdtemp(); port = 8898; U = f'http://127.0.0.1:{port}'
env = dict(os.environ, PORT=str(port), DATA_DIR=tmp, ADMIN_PASSWORD='Test-pass-1', PYTHONUTF8='1')
srv = subprocess.Popen([sys.executable, os.path.join(B, 'server.py')], env=env, cwd=B, stdout=subprocess.DEVNULL)
n = 0


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
        q = urllib.request.Request(U + path, body, hd, method=method)
        try:
            with s.op.open(q, timeout=120) as x:
                return x.status, x.read(), x.headers
        except urllib.error.HTTPError as e:
            return e.code, e.read(), e.headers

    def j(s, path, data=None, method=None, want=200):
        c, b, _ = s.r(path, data, method)
        ok(c == want, f'{method or ("POST" if data is not None else "GET")} {path} -> {c} {b[:200]}')
        return json.loads(b)

    def login(s, u, p):
        return s.j('/api/login', dict(user=u, password=p))


try:
    for _ in range(50):
        try:
            urllib.request.urlopen(U + '/', timeout=1); break
        except Exception:
            time.sleep(.2)
    a = S(); a.login('admin', 'Test-pass-1')
    # 계정: 임시 비밀번호 → 변경 강제
    r = a.j('/api/users', dict(users=[dict(login='w1', name='작업자1', dept='생산', site='전주', lang='vi'), dict(login='w2', name='작업자2', dept='생산', site='전주'), dict(login='m1', name='관리자1', dept='안전', role='manager')]))
    pw = {x['login']: x['password'] for x in r['created']}; ids = {x['login']: x['id'] for x in r['created']}
    w = S(); ok(w.login('w1', pw['w1'])['must_change'], 'must change')
    w.j('/api/my', want=403)
    w.j('/api/me/password', dict(old='x', new='Worker-pass-1'), want=400)
    w.j('/api/me/password', dict(old=pw['w1'], new='short'), want=400)
    w.j('/api/me/password', dict(old=pw['w1'], new='Worker-pass-1'))
    w.j('/api/me', want=401)           # 세션 무효화
    w.login('w1', 'Worker-pass-1')
    w2 = S(); w2.login('w2', pw['w2']); w2.j('/api/me/password', dict(old=pw['w2'], new='Worker-pass-2')); w2.login('w2', 'Worker-pass-2')
    # 권한
    for p in ['/api/users', '/api/matrix', '/api/audit', '/api/safety', '/api/alerts', '/api/dashboard', '/api/compare']:
        w.j(p, want=403)
    S().j('/api/manuals', want=401)
    w.j('/api/manuals', dict(title='x'), want=403)
    # 매뉴얼·업로드
    mid = a.j('/api/manuals', dict(title='프레스 안전작업', category='안전', dept='생산'))['id']
    a.j(f'/api/manuals/{mid}', dict(status='published'), 'PUT', want=400)   # 영상 없이 공개 불가
    ok(a.r(f'/api/manuals/{mid}/versions', raw=b'not a video')[0] == 400, 'reject non-video')
    video = open(os.path.join(B, 'tests/fixtures/sample.mp4'), 'rb').read()
    v1 = json.loads(a.r(f'/api/manuals/{mid}/versions', raw=video)[1])['version_id']

    def ready(v):
        for _ in range(240):
            s = a.j(f'/api/versions/{v}/status')
            if s['state'] != 'processing':
                return s
            time.sleep(.5)

    ok(ready(v1)['state'] == 'ready', 'transcode')
    m = a.j(f'/api/manuals/{mid}'); dur = m['version']['duration']; ok(dur > 2, 'duration')
    ok(a.r(f'/api/manuals/{mid}/versions', raw=video)[0] == 400, 'reason required')
    w.j(f'/api/manuals/{mid}', want=404); ok(w.r(f'/api/versions/{v1}/video')[0] == 404, 'draft hidden')
    a.j(f'/api/manuals/{mid}', dict(status='published'), 'PUT')
    # 스트리밍
    c, b, h = w.r(f'/api/versions/{v1}/video', headers={'Range': 'bytes=0-99'}); ok(c == 206 and len(b) == 100 and h['Content-Range'].startswith('bytes 0-99/'), 'range')
    ok(S().r(f'/api/versions/{v1}/video')[0] == 401, 'video auth')
    ok(a.r(f'/api/versions/{v1}/thumb')[1][:2] == b'\xff\xd8', 'thumb')
    # 단계
    a.j(f'/api/versions/{v1}/steps', dict(steps=[dict(start=5, end=1, title='x')]), 'PUT', want=400)
    a.j(f'/api/versions/{v1}/steps', dict(steps=[dict(start=0, end=dur / 2, title='보호구 착용', warn='턱끈 체결'), dict(start=dur / 2, end=dur, title='전원 켜기', note='점검 후')]), 'PUT')
    ok(len(a.j(f'/api/manuals/{mid}')['steps']) == 2, 'steps')
    # AI 자막
    a.j('/api/glossary', dict(term='안전화', replace_with='안전화(S등급)'))
    if AI:
        a.j(f'/api/versions/{v1}/subs/draft', {})
        for _ in range(600):
            j = [x for x in a.j(f'/api/versions/{v1}/status')['jobs'] if x['lang'] == 'ko'][0]
            if j['state'] != 'running':
                break
            time.sleep(1)
        ok(j['state'] == 'done', f'asr {j}')
        subs = a.j(f'/api/versions/{v1}/subs?lang=ko')['subs']; text = ' '.join(s['text'] for s in subs); print('ASR:', text)
        ok('안전모' in text and '안전화(S등급)' in text, 'asr text+glossary')
    else:
        subs = [dict(start=0, end=dur, text='안전모를 착용하십시오')]
    a.j(f'/api/versions/{v1}/subs/translate', dict(lang='vi'), want=400)   # 확정 전 번역 불가
    a.j(f'/api/versions/{v1}/subs', dict(lang='ko', confirm=True, subs=subs), 'PUT')
    if AI:
        a.j(f'/api/versions/{v1}/subs/translate', dict(lang='vi'))
        for _ in range(300):
            j = [x for x in a.j(f'/api/versions/{v1}/status')['jobs'] if x['lang'] == 'vi'][0]
            if j['state'] != 'running':
                break
            time.sleep(1)
        ok(j['state'] == 'done', f'translate {j}')
        vi = a.j(f'/api/versions/{v1}/subs?lang=vi')['subs']; print('VI:', vi[0]['text']); ok(vi and vi[0]['text'], 'vi text')
        a.j(f'/api/versions/{v1}/subs', dict(lang='vi', confirm=True, subs=vi), 'PUT')
    c, b, _ = w.r(f'/api/versions/{v1}/subs.vtt?lang=ko'); ok(c == 200 and b.startswith(b'WEBVTT') and b'-->' in b, 'vtt')
    # 배정·이수
    a.j(f'/api/manuals/{mid}/quiz', dict(quiz=[dict(question='착용할 것은?', options=['안전모', '모자'], answer=0)]), 'PUT')
    a.j(f'/api/manuals/{mid}/quiz', dict(quiz=[dict(question='x', options=['a'], answer=0)]), 'PUT', want=400)
    ok(a.j(f'/api/manuals/{mid}/assign', dict(dept='생산', due='2020-01-01'))['assigned'] == 2, 'assign dept')
    a.j(f'/api/manuals/{mid}/assign', {}, want=400)
    my = w.j('/api/my'); ok(my['assigned'][0]['st'] == 'todo', 'todo')
    ok('answer' not in w.j(f'/api/manuals/{mid}')['quiz'][0], 'answer hidden')
    sig = 'data:image/png;base64,iVBORw0KGgo='
    w.j(f'/api/manuals/{mid}/complete', dict(answers={}, signature=sig), want=400)   # 시청 미달
    w.j(f'/api/versions/{v1}/progress', dict(pct=95, lang='vi'))
    qid = str(w.j(f'/api/manuals/{mid}')['quiz'][0]['id'])
    w.j(f'/api/manuals/{mid}/complete', dict(answers={qid: 0}, signature='x'), want=400)  # 서명 없음
    ok(w.j(f'/api/manuals/{mid}/complete', dict(answers={qid: 1}, signature=sig))['passed'] is False, 'quiz fail')
    ok(w.j(f'/api/manuals/{mid}/complete', dict(answers={qid: 0}, signature=sig))['passed'], 'complete')
    ok(w.j('/api/my')['assigned'][0]['st'] == 'done', 'done'); ok(w.j('/api/my')['history'][0]['lang'] == 'vi', 'lang record')
    # 역량·미이수
    mx = a.j('/api/matrix'); ok(mx['cells'][f"{ids['w1']}:{mid}"]['st'] == 'done' and mx['capable'][str(mid)] == 1, 'matrix')
    un = a.j('/api/unfinished')['rows']; ok(len(un) == 1 and un[0]['name'] == '작업자2' and un[0]['overdue'], 'unfinished')
    for p, hd in [('/api/matrix.xlsx', '이름'), ('/api/unfinished.xlsx', '이름'), ('/api/completions.xlsx', '이수 시각')]:
        c, b, _ = a.r(p); ok(c == 200 and load_workbook(io.BytesIO(b)).active['A1'].value == hd, p)
    # 개정 → 재이수
    v2 = json.loads(a.r(f'/api/manuals/{mid}/versions', raw=video, headers={'X-Reason': quote('절차 변경')})[1])['version_id']
    ok(ready(v2)['state'] == 'ready', 'v2'); m = a.j(f'/api/manuals/{mid}')
    ok(m['current_version'] == v2 and len(m['versions']) == 2 and len(m['steps']) == 2 and m['versions'][0]['reason'] == '절차 변경', 'revision')
    ok(w.j('/api/my')['assigned'][0]['st'] == 'outdated', 'outdated')
    # 과정
    cid = a.j('/api/courses', dict(title='입사 교육', manual_ids=[mid]))['id']
    ok(a.j(f'/api/courses/{cid}/assign', dict(site='전주'))['assigned'] == 2, 'course assign')
    # 작업 분석
    ok(len(a.j('/api/compare')['versions']) == 2, 'compare')
    a.j('/api/compare/notes', dict(a=v1, b=v2, t=1.5, memo='순서 다름'))
    ok(a.j(f'/api/compare?a={v1}&b={v2}')['notes'][0]['memo'] == '순서 다름', 'note')
    a.j(f'/api/manuals/{mid}/standard', dict(version_id=v1)); a.j(f'/api/manuals/{mid}/standard', dict(version_id=99999), want=400)
    tid = a.j('/api/tasks', dict(title='순서 표준화', manual_id=mid, assignee_id=ids['w2'], due='2030-01-01', retrain_user_ids=[ids['w2']]))['id']
    w2.j(f'/api/tasks/{tid}', dict(status='doing'), 'PUT'); w.j(f'/api/tasks/{tid}', dict(status='done'), 'PUT', want=403)
    ok(len(w2.j('/api/tasks')['tasks']) == 1 and not w.j('/api/tasks')['tasks'], 'task scope')
    # 점검표
    a.j('/api/forms', dict(title='x', schema=[dict(label='a', type='zzz')]), want=400)
    fid = a.j('/api/forms', dict(title='프레스 일일점검', site='전주', schema=[dict(label='비상정지', type='check'), dict(label='유압', type='number', min=10, max=20), dict(label='비고', type='text')]))['id']
    w.j(f'/api/forms/{fid}/submit', dict(values={'0': True}), want=400)
    ok(not w.j(f'/api/forms/{fid}/submit', dict(values={'0': True, '1': 15, '2': '양호'}))['abnormal'], 'normal')
    ok(len(w.j(f'/api/forms/{fid}/submit', dict(values={'0': False, '1': 25}))['abnormal']) == 2, 'abnormal')
    al = a.j('/api/alerts')['rows']; ok(len(al) == 1 and '유압' in al[0]['message'], 'alert')
    a.j(f"/api/alerts/{al[0]['id']}/done", {})
    ok(len(a.j(f'/api/forms/{fid}/submissions')['rows']) == 2, 'subs')
    c, b, _ = a.r(f'/api/forms/{fid}/report.xlsx'); ok(c == 200 and load_workbook(io.BytesIO(b)).active.max_row == 3, 'form xlsx')
    # 중대재해
    sf = a.j('/api/safety'); ok(sf['total'] == 13, 'law items')
    w.j('/api/records', dict(kind='hazard', data=dict(title='프레스 방호장치 파손', body='A라인')))
    w.j('/api/records', dict(kind='opinion', data=dict(title='통로 협소', anon=True)))
    w.j('/api/records', dict(kind='budget', data=dict(title='x')), want=403)
    w.j('/api/records?kind=budget', want=403)
    ok(a.j('/api/records?kind=opinion')['rows'][0]['name'] == '작업자1', 'admin sees')
    m1 = S(); m1.login('m1', pw['m1']); m1.j('/api/me/password', dict(old=pw['m1'], new='Manager-pass-1')); m1.login('m1', 'Manager-pass-1')
    ok(m1.j('/api/records?kind=opinion')['rows'][0]['name'] == '익명', 'anon')
    rid = a.j('/api/records?kind=hazard')['rows'][0]['id']; a.j(f'/api/records/{rid}', dict(status='done', action='방호장치 교체'), 'PUT')
    h = sf['half']; a.j(f'/api/safety/{h}/4-3', dict(status='done', memo='반기 점검'), 'PUT'); a.j(f'/api/safety/{h}/9-9', dict(status='done'), 'PUT', want=404)
    a.j(f'/api/safety/{h}/4-3', dict(status='x'), 'PUT', want=400); a.j('/api/safety?half=zz', want=400)
    sf = a.j('/api/safety'); r43 = [r for r in sf['rows'] if r['code'] == '4-3'][0]; ok(r43['status'] == 'done' and r43['evidence'] == 1 and sf['done'] == 1, 'safety evidence')
    ok([r for r in sf['rows'] if r['code'] == '5-3'][0]['evidence']['total'] >= 2, 'edu evidence')
    c, b, _ = a.r(f'/api/safety/report.xlsx?half={h}'); ok(c == 200 and load_workbook(io.BytesIO(b)).active.max_row == 14, 'safety xlsx')
    # 현황·기록·계정
    d = a.j('/api/dashboard'); ok(d['manuals'] == 1 and d['users'] == 4, 'dashboard')
    au = a.j('/api/audit')['rows']; acts = {x['action'] for x in au}; ok({'login_ok', 'complete', 'safety_update', 'version_upload'} <= acts, f'audit {acts}')
    ok(a.r('/api/audit.xlsx')[0] == 200, 'audit xlsx')
    a.j(f"/api/users/{ids['w2']}", dict(active=False), 'PUT'); w2.j('/api/me', want=401); w2.j('/api/login', dict(user='w2', password='Worker-pass-2'), want=403)
    a.j('/api/users/1', dict(active=False), 'PUT', want=400)
    a.j('/api/users', dict(users=[dict(login='w1', name='중복')]), want=400)
    a.j('/api/logout', {}); a.j('/api/me', want=401)
    print(f'PASS {n} checks')
finally:
    srv.kill()
