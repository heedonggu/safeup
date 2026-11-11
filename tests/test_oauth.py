"""구글·카카오·네이버 로그인을 가짜 제공자 서버로 끝까지 확인한다.  실행: py tests/test_oauth.py"""
import base64, hashlib, http.cookiejar, json, os, subprocess, sys, tempfile, threading, time, urllib.error, urllib.parse, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

B = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP, PROV = 8896, 8897
U, PU = f'http://127.0.0.1:{APP}', f'http://127.0.0.1:{PROV}'
WHO = {}        # 다음 로그인에서 제공자가 돌려줄 사람
CODES = {}
n = 0


class Prov(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        u = urllib.parse.urlparse(self.path); qs = dict(urllib.parse.parse_qsl(u.query)); k = u.path.split('/')[1]
        if u.path.endswith('/auth'):
            assert qs['client_id'] == f'{k}-id' and qs['redirect_uri'] == f'{U}/auth/{k}/callback'
            code = os.urandom(8).hex(); CODES[code] = (k, dict(WHO[k]), qs.get('code_challenge'))
            self.send_response(302); self.send_header('Location', qs['redirect_uri'] + '?' + urllib.parse.urlencode({'code': code, 'state': qs['state']})); self.end_headers(); return
        if u.path.endswith('/me'):
            who = json.loads(base64.b64decode(self.headers['Authorization'].split()[1]))
            if k in ('google', 'sso'):
                body = {'sub': who['sub'], 'email': who['email'], 'email_verified': who['v'], 'name': who['name']}
            elif k == 'kakao':
                body = {'id': int(who['sub']), 'kakao_account': {'email': who['email'], 'is_email_valid': True, 'is_email_verified': who['v'], 'profile': {'nickname': who['name']}}}
            else:
                body = {'resultcode': '00', 'response': {'id': who['sub'], 'email': who['email'], 'name': who['name']}}
            b = json.dumps(body).encode(); self.send_response(200); self.send_header('Content-Type', 'application/json'); self.end_headers(); self.wfile.write(b)

    def do_POST(self):
        k = self.path.split('/')[1]
        d = dict(urllib.parse.parse_qsl(self.rfile.read(int(self.headers['Content-Length'])).decode()))
        kk, who, ch = CODES.pop(d['code'])
        good = kk == k and d['client_id'] == f'{k}-id' and d.get('client_' + 'secret') == f'{k}-key' and d['redirect_uri'] == f'{U}/auth/{k}/callback'
        if k in ('google', 'sso'):
            good &= base64.urlsafe_b64encode(hashlib.sha256(d['code_verifier'].encode()).digest()).rstrip(b'=').decode() == ch
        if k == 'naver':
            good &= bool(d.get('state'))
        b = json.dumps({'access_token': base64.b64encode(json.dumps(who).encode()).decode()} if good else {'error': 'invalid_grant'}).encode()
        self.send_response(200 if good else 400); self.send_header('Content-Type', 'application/json'); self.end_headers(); self.wfile.write(b)


ps = ThreadingHTTPServer(('127.0.0.1', PROV), Prov); threading.Thread(target=ps.serve_forever, daemon=True).start()
tmp = tempfile.mkdtemp()
cfg = {'base_url': U, 'owner_email': 'owner@example.com'}
for k in ('google', 'kakao', 'naver', 'sso'):
    cfg[k] = {'id': f'{k}-id', 'key': f'{k}-key', 'auth_url': f'{PU}/{k}/auth', 'exchange_url': f'{PU}/{k}/token', 'me_url': f'{PU}/{k}/me'}
cfg['sso'].update(domain='pkc.co.kr', label='피케이건설 계정')
json.dump(cfg, open(os.path.join(tmp, 'config.json'), 'w'))
srv = subprocess.Popen([sys.executable, os.path.join(B, 'server.py')], env=dict(os.environ, PORT=str(APP), DATA_DIR=tmp, ADMIN_PASSWORD='Test-pass-1', PYTHONUTF8='1'), cwd=B, stdout=subprocess.DEVNULL)


def ok(c, m):
    global n
    n += 1
    if not c:
        print('FAIL', m); srv.kill(); sys.exit(1)


class S:
    def __init__(s):
        s.cj = http.cookiejar.CookieJar()
        s.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(s.cj))

    def r(s, path, data=None, method=None):
        q = urllib.request.Request(path if path.startswith('http') else U + path, json.dumps(data).encode() if data is not None else None,
                                   {'Content-Type': 'application/json'} if data is not None else {}, method=method)
        try:
            with s.op.open(q, timeout=30) as x:
                return x.status, x.geturl(), x.read()
        except urllib.error.HTTPError as e:
            return e.code, e.geturl(), e.read()

    def j(s, path, data=None, method=None, want=200):
        c, _, b = s.r(path, data, method)
        ok(c == want, f'{path} -> {c} {b[:150]}')
        return json.loads(b)

    def social(s, k, who, link=False):
        WHO[k] = who
        c, url, _ = s.r(f'/auth/{k}/start' + ('?link=1' if link else ''))   # 리다이렉트를 끝까지 따라간다
        return url


try:
    for _ in range(50):
        try:
            urllib.request.urlopen(U + '/', timeout=1); break
        except Exception:
            time.sleep(.2)
    ok({p['id'] for p in S().j('/api/auth/providers')['providers']} == {'google', 'kakao', 'naver', 'sso'}, 'providers')
    # 1 대표 구글 → 최초 관리자에 연결
    o = S(); url = o.social('google', {'sub': 'g-owner', 'email': 'Owner@example.com', 'v': True, 'name': '대표'})
    ok(url.endswith('/app.html'), f'owner lands {url}')
    me = o.j('/api/me')['user']; ok(me['role'] == 'admin' and me['login'] == 'admin' and me['links'] == ['google'], f'owner admin {me}')
    # 2 관리자가 이메일로 등록한 직원 → 구글 확인 이메일로 바로 로그인
    r = o.j('/api/users', {'users': [{'login': 'kim', 'name': '김', 'email': 'kim@example.com'}, {'login': 'lee', 'name': '이'}]})
    o.j('/api/users', {'users': [{'login': 'kim2', 'name': '김2', 'email': 'KIM@example.com'}]}, want=400)
    k = S(); url = k.social('google', {'sub': 'g-kim', 'email': 'kim@example.com', 'v': True, 'name': '김'}); ok(url.endswith('/app.html'), 'email match')
    ok(k.j('/api/me')['user']['login'] == 'kim', 'kim')
    # 3 확인 안 된 이메일은 붙지 않고 가입 신청
    x = S(); url = x.social('google', {'sub': 'g-fake', 'email': 'kim@example.com', 'v': False, 'name': '사칭'})
    ok('login.html?err=' in url and '%EC%8A%B9%EC%9D%B8' in url, f'unverified pending {url}')
    x.j('/api/me', want=401)
    # 4 카카오 신규 → 신청 → 관리자 승인 → 로그인
    c = S(); url = c.social('kakao', {'sub': '777', 'email': 'new@example.com', 'v': True, 'name': '카카오신규'}); ok('err=' in url, 'kakao pending')
    users = o.j('/api/users')['users']; p = [u for u in users if u['login'] == 'kakao:777'][0]
    ok(not p['active'] and not p['has_pw'] and p['links'] == ['kakao'], 'pending row')
    o.j(f"/api/users/{p['id']}", {'active': True}, 'PUT')
    url = c.social('kakao', {'sub': '777', 'email': 'new@example.com', 'v': True, 'name': '카카오신규'}); ok(url.endswith('/app.html'), 'kakao after approve')
    ok(c.j('/api/me')['user']['name'] == '카카오신규', 'kakao me')
    c.j('/api/me/links/kakao', method='DELETE', want=400)   # 유일한 로그인 수단
    c.j('/api/me/password', {'new': 'Kakao-pass-11'})        # 소셜 계정의 비밀번호 만들기
    # 5 네이버: 비밀번호 사용자가 연결한 뒤 네이버로 로그인
    pw = r['created'][1]['password']
    l = S(); l.j('/api/login', {'user': 'lee', 'password': pw}); l.j('/api/me/password', {'old': pw, 'new': 'Lee-pass-1234'}); l.j('/api/login', {'user': 'lee', 'password': 'Lee-pass-1234'})
    url = l.social('naver', {'sub': 'n-lee', 'email': 'lee@naver.com', 'v': False, 'name': '이'}, link=True); ok(url.endswith('#/password'), f'link back {url}')
    ok(l.j('/api/me')['user']['links'] == ['naver'], 'linked')
    l2 = S(); url = l2.social('naver', {'sub': 'n-lee', 'email': 'x', 'v': False, 'name': '이'}); ok(url.endswith('/app.html') and l2.j('/api/me')['user']['login'] == 'lee', 'naver login')
    # 6 다른 사람에게 연결된 계정은 연결 거부
    url = k.social('naver', {'sub': 'n-lee', 'email': 'x', 'v': False, 'name': '이'}, link=True); ok('err=' in url, 'link conflict')
    # 7 위조·만료 상태값
    bad = S(); c0, url, _ = bad.r('/auth/google/callback?code=x&state=y'); ok('err=' in url, 'bad state')
    WHO['google'] = {'sub': 'g-kim', 'email': 'kim@example.com', 'v': True, 'name': '김'}
    s2 = S(); s2.op.addheaders = []
    nr = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(s2.cj), type('N', (urllib.request.HTTPRedirectHandler,), {'redirect_request': lambda *a: None})())
    try:
        nr.open(U + '/auth/google/start')
    except urllib.error.HTTPError as e:
        loc = e.headers['Location']
    ok(loc.startswith(PU) and 'code_challenge=' in loc and 'state=' in loc, 'pkce+state in auth url')
    st = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(loc).query))['state']
    c0, url, _ = S().r(f'/auth/google/callback?code=x&state={st}'); ok('err=' in url, 'state cookie required')
    c0, url, _ = s2.r(f'/auth/google/callback?error=access_denied&state={st}'); ok('err=' in url, 'user cancel')
    ok(S().r('/auth/github/start')[0] == 404, 'unknown provider')
    # 8 비활성화하면 소셜로도 못 들어옴
    o.j(f"/api/users/{[u for u in o.j('/api/users')['users'] if u['login'] == 'kim'][0]['id']}", {'active': False}, 'PUT')
    url = S().social('google', {'sub': 'g-kim', 'email': 'kim@example.com', 'v': True, 'name': '김'}); ok('err=' in url, 'inactive blocked')
    acts = {a['action'] for a in o.j('/api/audit')['rows']}; ok({'login_google', 'login_kakao', 'login_naver', 'link_naver'} <= acts, f'audit {acts}')
    # 9 관리 화면에서 설정 변경: 보안 키는 응답에 나오지 않고, 바로 적용된다
    st = o.j('/api/settings/login'); ok(all(p['has_key'] for p in st['providers'] if p['id'] != 'sso') and 'naver-key' not in json.dumps(st), 'settings hide key')
    l.j('/api/settings/login', want=403)
    o.j('/api/settings/login', {'naver': {'cid': '', 'key': ''}}, 'PUT')
    ok({p['id'] for p in S().j('/api/auth/providers')['providers']} == {'google', 'kakao', 'sso'}, 'naver disabled live')
    o.j('/api/settings/login', {'naver': {'cid': 'naver-id', 'key': ''}}, 'PUT')    # 빈 키는 기존 값 유지
    url = S().social('naver', {'sub': 'n-lee', 'email': 'x', 'v': False, 'name': '이'}); ok(url.endswith('/app.html'), 'naver re-enabled with kept key')
    ok('naver-key' in open(os.path.join(tmp, 'config.json'), encoding='utf8').read(), 'config persisted')
    # 10 회사 계정(SSO, OIDC): 회사 도메인은 바로 근로자, 다른 도메인은 가입 신청
    ok(any(p['id'] == 'sso' and p['label'] == '피케이건설 계정' for p in S().j('/api/auth/providers')['providers']), 'sso label')
    e = S(); url = e.social('sso', {'sub': 'oid-1', 'email': 'park@pkc.co.kr', 'v': True, 'name': '박현장'}); ok(url.endswith('/app.html'), f'sso domain lands {url}')
    me = e.j('/api/me')['user']; ok(me['role'] == 'worker' and me['email'] == 'park@pkc.co.kr' and me['links'] == ['sso'], f'sso worker {me}')
    url = S().social('sso', {'sub': 'oid-2', 'email': 'guest@other.com', 'v': True, 'name': '외부'}); ok('err=' in url, 'sso other domain pending')
    st = o.j('/api/settings/login'); sp = [p for p in st['providers'] if p['id'] == 'sso'][0]; ok(sp['domain'] == 'pkc.co.kr' and sp['sso_label'] == '피케이건설 계정' and sp['label'] == '피케이건설 계정', f'sso settings {sp}')
    o.j(f"/api/users/{[u for u in o.j('/api/users')['users'] if u['email'] == 'park@pkc.co.kr'][0]['id']}", {'active': False}, 'PUT')
    ok('err=' in S().social('sso', {'sub': 'oid-1', 'email': 'park@pkc.co.kr', 'v': True, 'name': '박현장'}), 'deactivated sso blocked')
    # 11 2단계 인증을 켠 계정은 소셜만으로 못 들어옴
    import sqlite3; d = sqlite3.connect(os.path.join(tmp, 'app.db')); d.execute("update users set totp='JBSWY3DPEHPK3PXP' where id=(select user_id from oauth_links where sub='n-lee')"); d.commit(); d.close()
    url = S().social('naver', {'sub': 'n-lee', 'email': 'x', 'v': False, 'name': '이'}); ok('err=' in url, '2fa blocks social-only login')
    print(f'PASS {n} checks')
finally:
    srv.kill(); ps.shutdown()
