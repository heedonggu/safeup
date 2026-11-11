"""정적 사이트(site/) + 접수 API + 서비스 API(product.py). 실행: py server.py
환경변수: PORT, HOST, ADMIN_PASSWORD, SECRET, DATA_DIR, COOKIE_SECURE, ASR_PYTHON, OLLAMA_URL, OLLAMA_MODEL"""
import base64, csv, hashlib, hmac, io, json, os, re, secrets, time
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, quote

import product
import oauth
import more
import extra  # noqa: F401 — 원작 대조로 더한 기능(라우트 등록)
import threading
from db import BASE, DATA, DB, one, q, x, pw_hash

SITE = os.path.join(BASE, 'site')
SECURE = '; Secure' if os.environ.get('COOKIE_SECURE') else ''


def _read(name, make):
    p = os.path.join(DATA, name)
    if not os.path.exists(p):
        open(p, 'w').write(make())
    return open(p).read().strip()


SECRET = os.environ.get('SECRET') or _read('secret.txt', lambda: secrets.token_hex(32))
KINDS = {'contact': ['company', 'name', 'email', 'message', 'category', 'phone'],
         'download': ['company', 'name', 'email', 'phone', 'employees', 'role', 'doc'],
         'survey': ['task'], 'agency': ['company', 'name', 'email', 'message']}
REQUIRED = {'contact': ['company', 'name', 'email', 'message', 'category'], 'download': ['company', 'name', 'email', 'phone', 'employees', 'role'],
            'survey': ['task'], 'agency': ['company', 'name', 'email', 'message']}
EMAIL = re.compile(r'^[^\s@]+@[^\s@]+\.[^\s@]+$')
PHONE = re.compile(r'^[0-9+()\-\s]{7,20}$')
MIME = {'.html': 'text/html; charset=utf-8', '.css': 'text/css; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.pdf': 'application/pdf', '.svg': 'image/svg+xml', '.png': 'image/png', '.ico': 'image/x-icon'}
hits = {}


def limited(key, n, add=True):
    now = time.time(); hits[key] = [t for t in hits.get(key, []) if now - t < 60] + ([now] if add else [])
    return len(hits[key]) > n


def init_admin():
    if one('select 1 x from users'):
        return
    old = DB.execute("select name from sqlite_master where name='admin'").fetchone() and one('select * from admin')
    if old:  # 이전 스키마의 관리자 비밀번호를 그대로 옮긴다
        x("insert into users(login,name,salt,hash,role) values(?,'관리자',?,?,'admin')", (old['user'], old['salt'], old['hash']))
        return
    pw = os.environ.get('ADMIN_PASSWORD') or secrets.token_urlsafe(12)
    salt = secrets.token_hex(16)
    x("insert into users(login,name,salt,hash,role) values('admin','관리자',?,?,'admin')", (salt, pw_hash(pw, salt)))
    if not os.environ.get('ADMIN_PASSWORD'):
        open(os.path.join(DATA, 'admin_initial_password.txt'), 'w').write(pw)
        print('관리자 초기 비밀번호를 data/admin_initial_password.txt 에 저장했습니다.')


def sign(msg):
    return hmac.new(SECRET.encode(), msg.encode(), hashlib.sha256).hexdigest()


def token(kind, ttl):
    exp = str(int(time.time()) + ttl)
    return f'{kind}.{exp}.{sign(kind + exp)}'


def valid(tok, kind):
    try:
        k, exp, sig = tok.split('.')
        return k == kind and int(exp) > time.time() and hmac.compare_digest(sig, sign(k + exp))
    except Exception:
        return False


class H(BaseHTTPRequestHandler):
    server_version = 'app'
    protocol_version = 'HTTP/1.1'

    def log_message(self, *a):
        pass

    def ip(self):
        # 터널(cloudflared)은 같은 서버에서 들어오므로 그때만 CF-Connecting-IP 를 믿는다
        ip, cf = self.client_address[0], (self.headers.get('CF-Connecting-IP') or '').strip()
        return cf if cf and ip in ('127.0.0.1', '::1') else ip

    def cross_site(self):
        # 다른 사이트에서 보낸 쓰기 요청 차단(브라우저는 POST·PUT·DELETE 에 Origin 을 붙인다)
        o = self.headers.get('Origin')
        if o and urlparse(o).netloc != self.headers.get('Host'):
            self.send(403, {'error': '허용되지 않은 요청입니다.'})
            return True
        return False

    def send(self, code, body=b'', ctype='application/json; charset=utf-8', cookies=(), extra=()):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header('Content-Type', ctype); self.send_header('Content-Length', str(len(body)))
        self.send_header('X-Content-Type-Options', 'nosniff'); self.send_header('Referrer-Policy', 'same-origin')
        self.send_header('X-Frame-Options', 'SAMEORIGIN')
        if SECURE:
            self.send_header('Strict-Transport-Security', 'max-age=31536000; includeSubDomains')
        if ctype.startswith('text/html'):
            self.send_header('Content-Security-Policy', "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; base-uri 'none'; form-action 'self'")
        self.send_header('Cache-Control', 'no-store' if ctype.startswith(('application/json', 'application/vnd', 'text/csv', 'text/vtt')) else 'no-cache')
        for k, v in extra:
            self.send_header(k, v)
        for c in cookies:
            self.send_header('Set-Cookie', c)
        self.end_headers(); self.wfile.write(body)

    def cookie(self, name):
        c = SimpleCookie(self.headers.get('Cookie', ''))
        return c[name].value if name in c else ''

    def user(self):
        tok = self.cookie('adm'); kind = tok.split('.')[0]
        m = re.fullmatch(r's(\d+)v(\d+)', kind)
        if not m or not valid(tok, kind):
            return None
        u = one('select * from users where id=? and active=1', (m[1],))
        return u if u and u['sv'] == int(m[2]) else None

    def body(self):
        n = int(self.headers.get('Content-Length') or 0)
        if n > 400_000 or 'application/json' not in (self.headers.get('Content-Type') or ''):
            self.close_connection = True
            return None
        try:
            d = json.loads(self.rfile.read(n) or b'{}')
            return d if isinstance(d, dict) else None
        except ValueError:
            return None

    def dispatch_api(self, method, path):
        for m, pat, role, raw, fn in product.routes:
            g = pat.match(path) if m == method else None
            if not g:
                continue
            if not more.ip_allowed(self.ip()):
                self.close_connection = raw
                return self.send(403, {'error': '허용되지 않은 접속 위치입니다.'})
            u = self.user()
            if not u:
                self.close_connection = raw
                return self.send(401, {'error': '로그인이 필요합니다.'})
            if not product.role_ok(u, role):
                self.close_connection = raw
                return self.send(403, {'error': '권한이 없습니다.'})
            if not extra.perm_ok(u, method, path):
                self.close_connection = raw
                return self.send(403, {'error': '이 기능을 쓸 권한이 없습니다. 관리자에게 요청하세요.'})
            if u['must_change'] and path not in ('/api/me', '/api/me/password'):
                self.close_connection = raw
                return self.send(403, {'error': '비밀번호를 먼저 변경하세요.', 'must_change': True})
            d = {}
            if not raw and method in ('POST', 'PUT'):
                d = self.body()
                if d is None:
                    return self.send(400, {'error': '잘못된 요청입니다.'})
            c = product.Ctx(self, u, parse_qs(urlparse(self.path).query), d)
            try:
                r = fn(c, *g.groups())
            except product.E as e:
                return self.send(e.code, {'error': e.msg})
            except Exception as e:
                print('ERR', method, path, repr(e))
                self.close_connection = raw
                return self.send(500, {'error': '서버 오류가 발생했습니다.'})
            if r is not product.Done:
                self.send(200, r)
            return True
        return False

    def do_GET(self):
        u = urlparse(self.path); p = u.path
        if SECURE and self.headers.get('X-Forwarded-Proto') == 'http':
            return self.go('https://' + (self.headers.get('Host') or '') + self.path)
        if p == '/api/leads' or p == '/api/leads.csv':
            me = self.user()
            if not more.ip_allowed(self.ip()):
                return self.send(403, {'error': '허용되지 않은 접속 위치입니다.'})
            if not me or not product.role_ok(me, 'manager'):
                return self.send(401, {'error': 'unauthorized'})
            k = parse_qs(u.query).get('kind', [''])[0]
            rows = q('select id,created,kind,data,status from leads' + (' where kind=?' if k else '') + ' order by id desc limit 1000', (k,) if k else ())
            leads = [dict(r, data=json.loads(r['data'])) for r in rows]
            if p.endswith('.csv'):
                out = io.StringIO(); w = csv.writer(out); w.writerow(['id', 'created', 'kind', 'status', 'data'])
                for l in leads:
                    d = json.dumps(l['data'], ensure_ascii=False)
                    w.writerow([l['id'], l['created'], l['kind'], l['status'], "'" + d if d[:1] in '=+-@' else d])
                return self.send(200, ('﻿' + out.getvalue()).encode(), 'text/csv; charset=utf-8')
            return self.send(200, {'leads': leads})
        if p == '/files/guide.pdf':
            if not valid(self.cookie('dl'), 'dl'):
                return self.send(403, '먼저 자료 청구 양식을 제출해 주세요.'.encode(), 'text/plain; charset=utf-8')
            return self.send(200, open(os.path.join(BASE, 'private', 'guide.pdf'), 'rb').read(), 'application/pdf')
        m = re.fullmatch(r'/auth/(google|kakao|naver|sso)/(start|callback)', p)
        if m:
            return self.oauth(m[1], m[2], parse_qs(u.query))
        if p == '/api/auth/providers':
            return self.send(200, {'providers': oauth.enabled()})
        if p.startswith('/api/'):
            if self.dispatch_api('GET', p) is False:
                self.send(404, {'error': 'not found'})
            return
        rel = 'index.html' if p == '/' else p.lstrip('/')
        f = os.path.realpath(os.path.join(SITE, rel))
        if os.path.isdir(f):
            f = os.path.join(f, 'index.html')
        if not f.startswith(os.path.realpath(SITE) + os.sep) or not os.path.isfile(f):
            return self.send(404, '찾을 수 없는 페이지입니다.'.encode(), 'text/plain; charset=utf-8')
        self.send(200, open(f, 'rb').read(), MIME.get(os.path.splitext(f)[1], 'application/octet-stream'))

    def go(self, loc, cookies=()):
        self.send(302, b'', 'text/plain', cookies=cookies, extra=[('Location', loc)])

    def oauth(self, k, step, qs):
        ip = self.ip()
        back = lambda msg: self.go('../../login.html?err=' + quote(msg), ['oas=; Path=/; Max-Age=0'])
        if not more.ip_allowed(ip):
            return back('허용되지 않은 접속 위치입니다.')
        arg = lambda n: qs.get(n, [''])[0]
        if step == 'start':
            link = None
            if arg('link'):
                me = self.user()
                if not me:
                    return back('먼저 로그인하세요.')
                link = me['id']
            try:
                url, st = oauth.start(k, link)
            except oauth.OAuthError as e:
                return back(str(e))
            raw = base64.urlsafe_b64encode(json.dumps(st).encode()).decode()
            return self.go(url, [f'oas={raw}.{sign(raw)}; Path=/; HttpOnly; SameSite=Lax; Max-Age=600{SECURE}'])
        try:
            raw, sig = self.cookie('oas').rsplit('.', 1)
            st = json.loads(base64.urlsafe_b64decode(raw)) if hmac.compare_digest(sig, sign(raw)) else None
        except Exception:
            st = None
        if not st or st.get('p') != k or not hmac.compare_digest(arg('state'), st.get('s', '')):
            return back('로그인 요청이 만료되었습니다. 다시 시도하세요.')
        if arg('error') or not arg('code'):
            return back('로그인을 취소했습니다.')
        try:
            u = oauth.resolve(k, *oauth.profile(k, arg('code'), st), link_uid=st.get('l'))
        except oauth.OAuthError as e:
            return back(str(e))
        x('insert into audit(user_id,action,target,ip) values(?,?,?,?)', (u['id'], ('link_' if st.get('l') else 'login_') + k, u['login'][:80], ip))
        if not u['active']:
            return back('가입 신청이 접수되었습니다. 관리자 승인 후 이용할 수 있습니다.')
        if u['totp'] and not st.get('l'):
            return back('2단계 인증을 켠 계정은 아이디·비밀번호와 인증 코드로 로그인하세요.')
        sess = f'adm={token(f"s{u["id"]}v{u["sv"]}", 8 * 3600)}; Path=/; HttpOnly; SameSite=Lax; Max-Age=28800{SECURE}'
        return self.go('../../app.html' + ('#/password' if st.get('l') else ''), ['oas=; Path=/; Max-Age=0', sess])

    def do_PUT(self):
        if self.cross_site():
            return
        p = urlparse(self.path).path
        if self.dispatch_api('PUT', p) is False:
            self.send(404, {'error': 'not found'})

    def do_DELETE(self):
        if self.cross_site():
            return
        p = urlparse(self.path).path
        if self.dispatch_api('DELETE', p) is False:
            self.send(404, {'error': 'not found'})

    def do_POST(self):
        if self.cross_site():
            return
        p = urlparse(self.path).path
        ip = self.ip()
        if p in ('/api/lead', '/api/login', '/api/logout', '/api/signup') or re.fullmatch(r'/api/leads/\d+/status', p):
            d = self.body()
            if d is None:
                return self.send(400, {'error': '잘못된 요청입니다.'})
        if p == '/api/lead':
            if limited('lead' + ip, 10):
                return self.send(429, {'error': '요청이 너무 많습니다. 잠시 뒤 다시 시도하세요.'})
            kind = d.get('kind')
            if kind not in KINDS:
                return self.send(400, {'error': '잘못된 요청입니다.'})
            vals = {k: str(d.get(k, '')).strip()[:2000] for k in KINDS[kind]}
            if any(not vals[k] for k in REQUIRED[kind]):
                return self.send(400, {'error': '필수 항목을 모두 입력하세요.'})
            if 'email' in vals and not EMAIL.match(vals['email']):
                return self.send(400, {'error': '이메일 형식이 올바르지 않습니다.'})
            if vals.get('phone') and not PHONE.match(vals['phone']):
                return self.send(400, {'error': '전화번호 형식이 올바르지 않습니다.'})
            if kind != 'survey' and not d.get('consent'):
                return self.send(400, {'error': '개인정보 처리방침에 동의해야 합니다.'})
            x('insert into leads(created,kind,data,ip) values(?,?,?,?)', (time.strftime('%Y-%m-%d %H:%M:%S'), kind, json.dumps(vals, ensure_ascii=False), ip))
            ck = [f'dl={token("dl", 3600)}; Path=/; HttpOnly; SameSite=Lax; Max-Age=3600{SECURE}'] if kind == 'download' else []
            return self.send(200, {'ok': True}, cookies=ck)
        if p == '/api/signup':
            if limited('signup' + ip, 5):
                return self.send(429, {'error': '요청이 너무 많습니다. 잠시 뒤 다시 시도하세요.'})
            name, email, pw = str(d.get('name', '')).strip()[:80], str(d.get('email', '')).strip().lower()[:200], str(d.get('password', ''))
            if not name or not EMAIL.match(email):
                return self.send(400, {'error': '이름과 올바른 이메일을 입력하세요.'})
            if len(pw) < 8:
                return self.send(400, {'error': '비밀번호는 8자 이상이어야 합니다.'})
            if not d.get('consent'):
                return self.send(400, {'error': '개인정보 처리방침에 동의해야 합니다.'})
            if one('select 1 x from users where login=? or lower(email)=?', (email, email)):
                return self.send(400, {'error': '이미 가입했거나 등록된 이메일입니다. 로그인하거나 관리자에게 문의하세요.'})
            salt = secrets.token_hex(16)
            uid = x("insert into users(login,name,salt,hash,role,dept,site,email,active,pending) values(?,?,?,?,'worker',?,?,?,0,1)",
                    (email, name, salt, pw_hash(pw, salt), str(d.get('dept', '')).strip()[:80], str(d.get('company', '')).strip()[:80], email))
            x('insert into audit(user_id,action,target,ip) values(?,?,?,?)', (uid, 'signup', email, ip))
            return self.send(200, {'ok': True, 'pending': True})
        if p == '/api/login':
            if not more.ip_allowed(ip):
                return self.send(403, {'error': '허용되지 않은 접속 위치입니다.'})
            if limited('login' + ip, 10, add=False):  # 실패만 센다: 한 공장 IP로 여러 명이 동시에 로그인한다
                return self.send(429, {'error': '시도가 너무 많습니다. 잠시 뒤 다시 시도하세요.'})
            login = str(d.get('user', '')).strip()
            u = one('select * from users where login=? or (lower(email)=? and email!="")', (login, login.lower()))
            ok = bool(u) and bool(u['hash']) and hmac.compare_digest(pw_hash(str(d.get('password', '')), u['salt']), u['hash'])
            if ok and not u['active']:
                return self.send(403, {'error': '관리자 승인을 기다리고 있습니다.' if u['pending'] else '사용이 중지된 계정입니다.'})
            if ok and u['totp']:
                if not d.get('otp'):
                    return self.send(401, {'error': '인증 앱의 6자리 코드를 입력하세요.', 'need_otp': True})
                ok = more.totp_ok(u['totp'], d.get('otp'))
            x('insert into audit(user_id,action,target,ip) values(?,?,?,?)', (u['id'] if u else None, 'login_ok' if ok else 'login_fail', login[:80], ip))
            if not ok:
                limited('login' + ip, 10)
                return self.send(401, {'error': '아이디 또는 비밀번호가 올바르지 않습니다.' if not (u and u['totp'] and d.get('otp')) else '인증 코드가 맞지 않습니다.', 'need_otp': bool(u and u['totp'] and d.get('otp'))})
            return self.send(200, {'ok': True, 'must_change': bool(u['must_change'])},
                             cookies=[f'adm={token(f"s{u["id"]}v{u["sv"]}", 8 * 3600)}; Path=/; HttpOnly; SameSite=Lax; Max-Age=28800{SECURE}'])
        if p == '/api/logout':
            u = self.user()
            if u:
                x('update users set sv=sv+1 where id=?', (u['id'],))
            return self.send(200, {'ok': True}, cookies=['adm=; Path=/; Max-Age=0'])
        m = re.fullmatch(r'/api/leads/(\d+)/status', p)
        if m:
            me = self.user()
            if not more.ip_allowed(self.ip()):
                return self.send(403, {'error': '허용되지 않은 접속 위치입니다.'})
            if not me or not product.role_ok(me, 'manager'):
                return self.send(401, {'error': 'unauthorized'})
            if d.get('status') not in ('new', 'done'):
                return self.send(400, {'error': '잘못된 상태입니다.'})
            x('update leads set status=? where id=?', (d['status'], int(m[1])))
            return self.send(200, {'ok': True})
        if self.dispatch_api('POST', p) is False:
            self.close_connection = True
            self.send(404, {'error': 'not found'})


if __name__ == '__main__':
    init_admin()
    threading.Thread(target=more.backup_loop, daemon=True).start()
    threading.Thread(target=more.mail_loop, daemon=True).start()
    threading.Thread(target=lambda: product.ollama('ok') if os.environ.get('OLLAMA_WARM') else None, daemon=True).start()  # 서버: 첫 AI 요청이 모델 적재(약 1분)를 기다리지 않게
    x("update versions set state='failed',error='서버 재시작으로 변환이 중단되었습니다. 다시 올려 주세요.' where state='processing'")
    x("update subjobs set state='failed',error='서버 재시작으로 중단되었습니다.' where state='running'")
    port = int(os.environ.get('PORT', 8800))
    print(f'http://localhost:{port}/', flush=True)
    ThreadingHTTPServer((os.environ.get('HOST', '127.0.0.1'), port), H).serve_forever()
