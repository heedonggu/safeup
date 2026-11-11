"""구글·카카오·네이버 로그인(OAuth 2.0 인가 코드 방식).
설정은 git 에서 제외된 data/config.json 또는 환경변수에서만 읽는다.
  data/config.json: {"base_url", "owner_email", "google": {"id", "key"}, "kakao": {...}, "naver": {...}}
  환경변수: BASE_URL, OWNER_EMAIL, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_KEY (KAKAO_, NAVER_ 동일)
계정 연결 규칙: ① 이미 연결된 소셜 계정 ② 제공자가 확인한 이메일(구글·카카오)과 같은 이메일의 사용자 ③ 대표 이메일(owner_email)은 관리자
④ 그 밖에는 비활성 가입 신청으로 만들고 관리자가 사용자 화면에서 활성화한다. 네이버는 이메일 확인 여부를 주지 않아 ①·④만 쓴다."""
import base64, hashlib, json, os, secrets, urllib.parse, urllib.request

from db import DATA, one, q, x, DB, LOCK

DB.execute('create table if not exists oauth_links(provider text, sub text, user_id int references users(id), created text default current_timestamp, primary key(provider, sub))')
if 'email' not in [r[1] for r in DB.execute('pragma table_info(users)').fetchall()]:
    DB.execute("alter table users add column email text default ''")
DB.commit()

_cfg_path = os.path.join(DATA, 'config.json')
CFG = json.load(open(_cfg_path, encoding='utf8')) if os.path.exists(_cfg_path) else {}
BASE_URL = (os.environ.get('BASE_URL') or CFG.get('base_url') or 'http://localhost:8800').rstrip('/')
OWNERS = {e.strip().lower() for e in (os.environ.get('OWNER_EMAIL') or CFG.get('owner_email') or '').split(',') if e.strip()}

P = {
    'google': dict(label='Google', auth_url='https://accounts.google.com/o/oauth2/v2/auth', exchange_url='https://oauth2.googleapis.com/token',
                   me_url='https://openidconnect.googleapis.com/v1/userinfo', scope='openid email profile', pkce=True),
    'kakao': dict(label='카카오', auth_url='https://kauth.kakao.com/oauth/authorize', exchange_url='https://kauth.kakao.com/oauth/token',
                  me_url='https://kapi.kakao.com/v2/user/me', scope='profile_nickname account_email', pkce=False),
    'naver': dict(label='네이버', auth_url='https://nid.naver.com/oauth2.0/authorize', exchange_url='https://nid.naver.com/oauth2.0/token',
                  me_url='https://openapi.naver.com/v1/nid/me', scope='', pkce=False),
    # 회사 계정(SSO): 표준 OIDC 를 쓰는 조직 로그인(Microsoft Entra ID, Google Workspace, Okta, Keycloak 등). 발급자(issuer)만 넣으면 주소는 자동으로 찾는다
    'sso': dict(label='회사 계정(SSO)', auth_url='', exchange_url='', me_url='', scope='openid email profile', pkce=True),
}
SSO_EXTRA = ('issuer', 'domain', 'label', 'auth_url', 'exchange_url', 'me_url')


def _discover(p):
    """issuer 의 .well-known 설정에서 로그인·토큰·사용자 정보 주소를 읽는다."""
    iss = (CFG.get('sso') or {}).get('issuer', '').rstrip('/')
    if iss and not p['auth_url']:
        d = json.load(urllib.request.urlopen(iss + '/.well-known/openid-configuration', timeout=15))
        p['auth_url'], p['exchange_url'], p['me_url'] = d['authorization_endpoint'], d['token_endpoint'], d['userinfo_endpoint']


def _conf(k, field):
    return os.environ.get(f'{k.upper()}_CLIENT_{field.upper()}') or (CFG.get(k) or {}).get(field, '')


def _apply():
    for k, p in P.items():
        p['cid'], p['ck'] = _conf(k, 'id'), _conf(k, 'key')
        for e in ('auth_url', 'exchange_url', 'me_url'):  # 시험용 대체 주소, SSO 직접 지정
            if (CFG.get(k) or {}).get(e):
                p[e] = CFG[k][e]
    P['sso']['label'] = (CFG.get('sso') or {}).get('label') or '회사 계정(SSO)'


_apply()


class OAuthError(Exception):
    pass


def enabled():
    return [{'id': k, 'label': p['label']} for k, p in P.items() if p['cid']]


def redirect_uri(k):
    return f'{BASE_URL}/auth/{k}/callback'


def start(k, link_uid=None):
    """(제공자 로그인 주소, 쿠키에 넣을 상태) 반환."""
    p = P.get(k)
    if not p or not p['cid']:
        raise OAuthError('이 로그인 방식은 설정되지 않았습니다.')
    if k == 'sso':
        try:
            _discover(p)
        except Exception:
            raise OAuthError('회사 로그인 서버(issuer)에 연결하지 못했습니다.')
        if not p['auth_url']:
            raise OAuthError('회사 계정 로그인 주소가 설정되지 않았습니다.')
    st = {'p': k, 's': secrets.token_urlsafe(24), 'l': link_uid}
    a = {'response_type': 'code', 'client_id': p['cid'], 'redirect_uri': redirect_uri(k), 'state': st['s']}
    if p['scope']:
        a['scope'] = p['scope']
    if p['pkce']:
        st['v'] = secrets.token_urlsafe(48)
        a['code_challenge'] = base64.urlsafe_b64encode(hashlib.sha256(st['v'].encode()).digest()).rstrip(b'=').decode()
        a['code_challenge_method'] = 'S256'
    if k == 'google':
        a['prompt'] = 'select_account'
    return p['auth_url'] + '?' + urllib.parse.urlencode(a), st


def _post(url, data):
    r = urllib.request.Request(url, urllib.parse.urlencode(data).encode(), {'Content-Type': 'application/x-www-form-urlencoded;charset=utf-8', 'Accept': 'application/json'})
    return json.load(urllib.request.urlopen(r, timeout=15))


def _get(url, bearer):
    return json.load(urllib.request.urlopen(urllib.request.Request(url, headers={'Authorization': 'Bearer ' + bearer, 'Accept': 'application/json'}), timeout=15))


def profile(k, code, st):
    """인가 코드를 접근 토큰으로 바꾸고 (sub, email, email_verified, name) 반환."""
    p = P[k]
    d = {'grant_type': 'authorization_code', 'client_id': p['cid'], 'code': code, 'redirect_uri': redirect_uri(k)}
    if p['ck']:
        d['client_' + 'secret'] = p['ck']   # 표준 파라미터 이름, 값은 설정에서 읽음
    if k == 'naver':
        d['state'] = st['s']
    if st.get('v'):
        d['code_verifier'] = st['v']
    try:
        access = _post(p['exchange_url'], d).get('access_token')
        if not access:
            raise OAuthError('로그인 토큰을 받지 못했습니다.')
        me = _get(p['me_url'], access)
    except OAuthError:
        raise
    except Exception:
        raise OAuthError('로그인 제공자와 통신하지 못했습니다.')
    if k == 'sso':
        email = (me.get('email') or me.get('preferred_username') or me.get('upn') or '').lower()
        return str(me['sub']), email, bool(me.get('email_verified', True) and email), me.get('name') or email or '회사 사용자'
    if k == 'google':
        return str(me['sub']), (me.get('email') or '').lower(), bool(me.get('email_verified')), me.get('name') or me.get('email') or 'Google 사용자'
    if k == 'kakao':
        ka = me.get('kakao_account') or {}
        return str(me['id']), (ka.get('email') or '').lower(), bool(ka.get('is_email_valid') and ka.get('is_email_verified')), (ka.get('profile') or {}).get('nickname') or '카카오 사용자'
    r = me.get('response') or {}
    if not r.get('id'):
        raise OAuthError('네이버 사용자 정보를 받지 못했습니다.')
    return str(r['id']), (r.get('email') or '').lower(), False, r.get('name') or r.get('nickname') or '네이버 사용자'


def resolve(k, sub, email, verified, name, link_uid=None):
    """로그인할 사용자 행을 돌려준다. 새 사람은 비활성 가입 신청으로 만든다."""
    with LOCK:
        if link_uid:
            other = one('select user_id from oauth_links where provider=? and sub=?', (k, sub))
            if other and other['user_id'] != link_uid:
                raise OAuthError('이 계정은 이미 다른 사용자에게 연결되어 있습니다.')
            x('insert or replace into oauth_links(provider,sub,user_id) values(?,?,?)', (k, sub, link_uid))
            return one('select * from users where id=?', (link_uid,))
        l = one('select user_id from oauth_links where provider=? and sub=?', (k, sub))
        if l:
            return one('select * from users where id=?', (l['user_id'],))
        u = None
        if verified and email:
            u = one("select * from users where lower(email)=? and email!=''", (email,))
            if not u and email in OWNERS:  # 대표 이메일: 이메일이 비어 있는 최초 관리자에 붙이거나 새 관리자로 만든다
                u = one("select * from users where login='admin' and email=''")
                if u:
                    x('update users set email=? where id=?', (email, u['id']))
                else:
                    uid = x("insert into users(login,name,role,email) values(?,?,'admin',?)", (f'{k}:{sub}', name[:80], email))
                    u = one('select * from users where id=?', (uid,))
        dom = (CFG.get('sso') or {}).get('domain', '').lower().lstrip('@')
        if not u and k == 'sso' and verified and dom and email.endswith('@' + dom):  # 회사 도메인 계정은 바로 근로자로 쓴다(퇴사 등은 관리자가 비활성화)
            uid = x('insert into users(login,name,role,active,email) values(?,?,?,1,?)', (f'{k}:{sub}', name[:80], 'worker', email))
            u = one('select * from users where id=?', (uid,))
        if not u:
            uid = x('insert into users(login,name,role,active,email) values(?,?,?,0,?)', (f'{k}:{sub}', name[:80], 'worker', email if verified else ''))
            u = one('select * from users where id=?', (uid,))
        x('insert or replace into oauth_links(provider,sub,user_id) values(?,?,?)', (k, sub, u['id']))
        return u


def settings():
    """관리 화면용. 비밀 값은 돌려주지 않고 설정 여부만 알린다."""
    return {'base_url': BASE_URL, 'owner_email': ', '.join(sorted(OWNERS)),
            'providers': [{'id': k, 'label': p['label'], 'cid': p['cid'], 'has_key': bool(p['ck']), 'redirect_uri': redirect_uri(k),
                           'console': {'google': 'https://console.cloud.google.com/auth/clients', 'kakao': 'https://developers.kakao.com/console/app',
                                       'naver': 'https://developers.naver.com/apps/#/register', 'sso': ''}[k],
                           **({('sso_label' if e == 'label' else e): (CFG.get('sso') or {}).get(e, '') for e in SSO_EXTRA} if k == 'sso' else {})} for k, p in P.items()]}


def save(d):
    """설정을 data/config.json 에 쓰고 바로 적용한다. 빈 key 는 기존 값을 유지한다."""
    global BASE_URL, OWNERS
    cfg = dict(CFG)
    if 'base_url' in d:
        cfg['base_url'] = str(d['base_url']).strip().rstrip('/')[:200]
    if 'owner_email' in d:
        cfg['owner_email'] = str(d['owner_email']).strip()[:500]
    for k in P:
        v = d.get(k)
        if isinstance(v, dict):
            c = dict(cfg.get(k) or {})
            c['id'] = str(v.get('cid', c.get('id', ''))).strip()[:300]
            if str(v.get('key') or '').strip():
                c['key'] = str(v['key']).strip()[:300]
            if v.get('clear'):
                c.pop('key', None); c['id'] = ''
            if k == 'sso':
                for e in SSO_EXTRA:
                    if e in v:
                        c[e] = str(v[e]).strip()[:300]
            cfg[k] = c
    tmp = _cfg_path + '.tmp'
    with open(tmp, 'w', encoding='utf8') as f:
        json.dump(cfg, f, ensure_ascii=False, indent=1)
    os.replace(tmp, _cfg_path)
    CFG.clear(); CFG.update(cfg)
    BASE_URL = (os.environ.get('BASE_URL') or CFG.get('base_url') or 'http://localhost:8800').rstrip('/')
    OWNERS = {e.strip().lower() for e in (os.environ.get('OWNER_EMAIL') or CFG.get('owner_email') or '').split(',') if e.strip()}
    for e in ('auth_url', 'exchange_url', 'me_url'):
        P['sso'][e] = ''
    _apply()


def links(uid):
    return [r['provider'] for r in q('select provider from oauth_links where user_id=?', (uid,))]
