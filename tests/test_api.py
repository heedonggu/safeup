"""실서버를 임시 데이터 폴더로 띄워 접수·다운로드 제한·관리자 흐름을 확인한다.  실행: py tests/test_api.py"""
import http.cookiejar, json, os, subprocess, sys, tempfile, time, urllib.request, urllib.error
B = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
tmp = tempfile.mkdtemp(); port = 8899
env = dict(os.environ, PORT=str(port), DATA_DIR=tmp, ADMIN_PASSWORD='Test-pass-1', PYTHONUTF8='1')
srv = subprocess.Popen([sys.executable, os.path.join(B, 'server.py')], env=env, stdout=subprocess.DEVNULL, cwd=B)
U = f'http://127.0.0.1:{port}'
def req(path, data=None, cj=None, ctype='application/json', method=None, hd=None):
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj)) if cj is not None else urllib.request.build_opener()
    r = urllib.request.Request(U + path, data=(json.dumps(data).encode() if isinstance(data, (dict, list)) else data), method=method,
                               headers=dict({'Content-Type': ctype} if data is not None else {}, **(hd or {})))
    try:
        with op.open(r) as x: return x.status, x.read()
    except urllib.error.HTTPError as e: return e.code, e.read()
n = 0
def ok(c, m):
    global n; n += 1
    if not c: print('FAIL', m); srv.kill(); sys.exit(1)
try:
    for _ in range(50):
        try: urllib.request.urlopen(U + '/', timeout=1); break
        except Exception: time.sleep(.2)
    pages = [os.path.relpath(os.path.join(d, f), os.path.join(B, 'site')).replace(os.sep, '/') for d, _, fs in os.walk(os.path.join(B, 'site')) for f in fs if f.endswith('.html')]
    ok(len(pages) >= 30, f'pages {len(pages)}')
    for p in pages: ok(req('/' + p)[0] == 200, p)
    ok(req('/../server.py')[0] == 404 and req('/%2e%2e/server.py')[0] == 404, 'traversal')
    ok(req('/files/guide.pdf')[0] == 403, 'pdf without cookie')
    good = dict(kind='download', company='A', name='B', email='a@b.co', phone='010-1234-5678', employees='50명 미만', role='기타', consent=True)
    ok(req('/api/lead', dict(good, email='bad'))[0] == 400, 'bad email')
    ok(req('/api/lead', dict(good, consent=False))[0] == 400, 'no consent')
    ok(req('/api/lead', dict(good, company=''))[0] == 400, 'missing field')
    ok(req('/api/lead', b'x=1', ctype='text/plain')[0] == 400, 'non-json')
    ok(req('/api/lead', dict(good, kind='zzz'))[0] == 400, 'bad kind')
    cj = http.cookiejar.CookieJar()
    ok(req('/api/lead', good, cj)[0] == 200, 'download lead')
    c, b = req('/files/guide.pdf', cj=cj); ok(c == 200 and b[:4] == b'%PDF', 'pdf with cookie')
    ok(req('/api/lead', dict(kind='contact', company='A', name='B', email='a@b.co', message='=cmd', category='기타', consent=True))[0] == 200, 'contact')
    ok(req('/api/lead', dict(kind='survey', task='기타'))[0] == 200, 'survey')
    ok(req('/api/leads')[0] == 401 and req('/api/leads.csv')[0] == 401, 'admin gate')
    ok(req('/api/login', dict(user='admin', password='x'))[0] == 401, 'bad login')
    adm = http.cookiejar.CookieJar()
    ok(req('/api/login', dict(user='admin', password='Test-pass-1'), adm)[0] == 200, 'login')
    leads = json.loads(req('/api/leads', cj=adm)[1])['leads']; ok(len(leads) == 3, f'leads {len(leads)}')
    ok(req(f'/api/leads/{leads[0]["id"]}/status', dict(status='done'), adm)[0] == 200, 'status')
    ok(req(f'/api/leads/{leads[0]["id"]}/status', dict(status='x'), adm)[0] == 400, 'bad status')
    ok(req('/api/leads/1/status', dict(status='done'))[0] == 401, 'status gate')
    c, b = req('/api/leads.csv?kind=contact', cj=adm); ok(c == 200 and 'contact' in b.decode('utf8'), 'csv')
    codes = [req('/api/lead', dict(good), hd={'CF-Connecting-IP': '203.0.113.7'})[0] for _ in range(12)]; ok(429 in codes, 'rate limit')
    ok(req('/api/lead', dict(good), hd={'CF-Connecting-IP': '203.0.113.8'})[0] == 200, 'rate limit per real ip')
    ok(req('/api/lead', dict(good), hd={'Origin': 'https://evil.example'})[0] == 403, 'cross-site blocked')
    ok(req('/api/lead', dict(good), hd={'Origin': U, 'CF-Connecting-IP': '203.0.113.9'})[0] == 200, 'same-site ok')
    print(f'PASS {n} checks')
finally:
    srv.kill()
