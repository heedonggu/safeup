"""서비스 본체 API: 영상 매뉴얼, 이수·역량, AI 자막, 작업 분석, 점검표, 중대재해 의무 관리, 계정·접속 기록."""
import base64, io, json, os, re, secrets, shutil, subprocess, sys, threading, time, urllib.request, uuid
from datetime import date

from db import BASE, VIDEOS, one, q, x, many, pw_hash
import oauth

# 안전보건 웹앱(pk_construction_brain/webapp)과 합칠 때: 이수 기록을 그 앱 /api/edu/complete 로 보내고, 안전 메뉴는 그 앱 화면으로 연결한다
SAFETY_ORIGIN = os.environ.get('SAFETY_ORIGIN', '').rstrip('/')
EDU_SECRET = os.environ.get('EDU_SECRET') or (open(os.environ['EDU_SECRET_FILE'], encoding='utf8').read().strip() if os.environ.get('EDU_SECRET_FILE') else '')


def send_edu(body):
    if not (SAFETY_ORIGIN and EDU_SECRET):
        return
    try:
        r = urllib.request.Request(SAFETY_ORIGIN + '/api/edu/complete', json.dumps(body, ensure_ascii=False).encode('utf8'), {'Content-Type': 'application/json', 'x-edu-secret': EDU_SECRET})
        urllib.request.urlopen(r, timeout=10).read()
    except Exception as ex:  # 안전 앱이 꺼져 있어도 이수 처리는 끝낸다. 실패는 접속 기록에 남긴다
        x('insert into audit(action,target) values(?,?)', ('edu_sync_fail', f"{body.get('ref')}: {ex}"[:200]))


ASR_PY = os.environ.get('ASR_PYTHON', r'C:\Users\USER\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe')
OLLAMA = os.environ.get('OLLAMA_URL', 'http://127.0.0.1:11434')
OLLAMA_MODEL = os.environ.get('OLLAMA_MODEL', 'qwen3:8b')
MAX_VIDEO = int(os.environ.get('MAX_UPLOAD_MB', 95)) * 1024 ** 2  # 클라우드플레어 무료 요금제 요청 한도 100MB
PASS_SCORE = 80      # 확인 테스트 합격선(%)
WATCH_MIN = 90       # 이수에 필요한 시청률(%)
ROLES = {'worker': 1, 'manager': 2, 'admin': 3}
LANGS = {'ko': '한국어', 'en': 'English', 'vi': 'Tiếng Việt', 'zh': '中文', 'th': 'ไทย', 'ne': 'नेपाली', 'id': 'Bahasa Indonesia', 'uz': 'Oʻzbek',
         'ja': '日本語', 'km': 'ភាសាខ្មែរ', 'mn': 'Монгол', 'my': 'မြန်မာ', 'ru': 'Русский', 'fil': 'Filipino', 'bn': 'বাংলা', 'ur': 'اردو',
         'si': 'සිංහල', 'lo': 'ລາວ', 'kk': 'Қазақ', 'hi': 'हिन्दी', 'ar': 'العربية', 'es': 'Español', 'fr': 'Français', 'de': 'Deutsch',
         'pt': 'Português', 'tr': 'Türkçe', 'uk': 'Українська'}
RECORD_KINDS = {'hazard', 'budget', 'evaluation', 'opinion', 'drill', 'contractor', 'legal'}
WORKER_KINDS = {'hazard', 'opinion'}

# 중대재해 처벌 등에 관한 법률 시행령(대통령령, 시행 2025-10-01) 제4조·제5조 대조. half=True 는 조문상 '반기 1회 이상' 점검 항목.
LAW = [
    ('4-1', '제4조제1호', '안전·보건 목표와 경영방침 설정', False, ''),
    ('4-2', '제4조제2호', '안전·보건 업무 총괄·관리 전담 조직 (해당 사업장)', False, ''),
    ('4-3', '제4조제3호', '유해·위험요인 확인·개선 절차 마련 및 점검', True, 'hazard'),
    ('4-4', '제4조제4호', '재해 예방 예산 편성 및 용도에 맞는 집행', False, 'budget'),
    ('4-5', '제4조제5호', '안전보건관리책임자등 권한·예산 부여, 평가기준 마련 및 평가·관리', True, 'evaluation'),
    ('4-6', '제4조제6호', '안전관리자·보건관리자 등 전문인력 배치', False, ''),
    ('4-7', '제4조제7호', '종사자 의견 청취 절차, 개선방안 마련·이행 점검', True, 'opinion'),
    ('4-8', '제4조제8호', '중대산업재해 대비 매뉴얼 마련 및 조치 점검', True, 'drill'),
    ('4-9', '제4조제9호', '도급·용역·위탁 시 평가기준·관리비용·기간 기준 마련 및 점검', True, 'contractor'),
    ('5-1', '제5조제2항제1호', '안전·보건 관계 법령 의무 이행 점검 또는 결과 보고', True, 'legal'),
    ('5-2', '제5조제2항제2호', '미이행 의무에 인력·예산 등 필요한 조치', False, 'legal'),
    ('5-3', '제5조제2항제3호', '유해·위험 작업 안전·보건 교육 실시 점검', True, 'edu'),
    ('5-4', '제5조제2항제4호', '미실시 교육 이행 지시, 예산 확보 등 조치', False, 'edu'),
]
routes = []
AFTER_SUBS = []
BEFORE_SAVE = []   # (종류, 버전, 사용자) 덮어쓰기 전 이력 남기기(extra.py)
AFTER_UPLOAD = []  # (버전, 사용자, 자동 처리 여부)
voice_for = lambda lang: None  # extra.py 가 채운다


def setting(k, default=''):
    r = one('select v from settings where k=?', (k,))
    return r['v'] if r else default


class E(Exception):
    def __init__(self, code, msg):
        self.code, self.msg = code, msg


class Done:
    """핸들러가 응답을 직접 보냈음을 뜻한다."""


def route(method, pat, role='worker', raw=False):
    def deco(fn):
        routes.append((method, re.compile('^' + pat + '$'), role, raw, fn))
        return fn
    return deco


class Ctx:
    def __init__(self, h, user, query, body):
        self.h, self.u, self.q, self.d = h, user, query, body

    def arg(self, k, default=''):
        return self.q.get(k, [default])[0]

    def log(self, action, target=''):
        x('insert into audit(user_id,action,target,ip) values(?,?,?,?)', (self.u['id'] if self.u else None, action, str(target)[:200], self.h.ip()))


def s(d, k, n=500, req=False):
    v = str(d.get(k, '') or '').strip()[:n]
    if req and not v:
        raise E(400, f'{k} 값이 필요합니다.')
    return v


def need(row, msg='찾을 수 없습니다.'):
    if not row:
        raise E(404, msg)
    return row


def fnum(v, name='숫자'):
    try:
        f = float(v)
    except (TypeError, ValueError):
        raise E(400, f'{name} 값이 올바르지 않습니다.')
    if f != f or f in (float('inf'), float('-inf')):
        raise E(400, f'{name} 값이 올바르지 않습니다.')
    return f


def role_ok(u, role):
    return ROLES.get(u['role'], 0) >= ROLES[role]


def xlsx(c, name, headers, rows):
    from openpyxl import Workbook
    wb = Workbook(); ws = wb.active; ws.append(headers)
    for r in rows:  # 수식 주입 방지
        ws.append([("'" + v if isinstance(v, str) and v[:1] in '=+-@' else v) for v in r])
    b = io.BytesIO(); wb.save(b)
    c.h.send(200, b.getvalue(), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
             extra=[('Content-Disposition', f'attachment; filename="{name}.xlsx"')])
    return Done


# ---------- 계정 ----------
def public_user(u):
    d = {k: u[k] for k in ('id', 'login', 'name', 'role', 'dept', 'site', 'lang', 'active', 'must_change', 'email', 'pending')}
    d['totp'] = bool(u['totp'])
    d['has_pw'] = bool(u['hash'])
    d['links'] = oauth.links(u['id'])
    return d


@route('GET', r'/api/me')
def me(c):
    return {'user': public_user(c.u), 'langs': LANGS, 'providers': oauth.enabled(), 'safety': bool(SAFETY_ORIGIN), 'alerts': one('select count(*) n from alerts where done=0')['n'] if role_ok(c.u, 'manager') else 0}


@route('POST', r'/api/me/password')
def change_pw(c):
    new = str(c.d.get('new', ''))
    if len(new) < 8:
        raise E(400, '비밀번호는 8자 이상이어야 합니다.')
    if c.u['hash'] and pw_hash(str(c.d.get('old', '')), c.u['salt']) != c.u['hash']:
        raise E(400, '현재 비밀번호가 올바르지 않습니다.')
    salt = secrets.token_hex(16)
    x('update users set salt=?,hash=?,must_change=0,sv=sv+1 where id=?', (salt, pw_hash(new, salt), c.u['id']))
    c.log('password_change')
    return {'ok': True, 'relogin': True}


@route('GET', r'/api/users', 'manager')
def users(c):
    return {'users': [public_user(u) for u in q('select * from users order by active desc, dept, name')]}


def check_email(d, uid=0):
    email = s(d, 'email', 200).lower()
    if email and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email):
        raise E(400, f'이메일 형식이 올바르지 않습니다: {email}')
    if email and one('select 1 x from users where lower(email)=? and id!=?', (email, uid)):
        raise E(400, f'이미 등록된 이메일입니다: {email}')
    return email


def add_user(d):
    login, name = s(d, 'login', 80, True), s(d, 'name', 80, True)
    role = d.get('role') or 'worker'
    if role not in ROLES:
        raise E(400, '권한 값이 올바르지 않습니다.')
    lang = d.get('lang') or 'ko'
    if lang not in LANGS:
        raise E(400, '언어 값이 올바르지 않습니다.')
    if one('select 1 x from users where login=?', (login,)):
        raise E(400, f'이미 있는 아이디입니다: {login}')
    email = check_email(d)
    pw = secrets.token_urlsafe(9); salt = secrets.token_hex(16)
    uid = x('insert into users(login,name,salt,hash,role,dept,site,lang,must_change,email) values(?,?,?,?,?,?,?,?,1,?)',
            (login, name, salt, pw_hash(pw, salt), role, s(d, 'dept', 80), s(d, 'site', 80), lang, email))
    return uid, pw


@route('POST', r'/api/users', 'admin')
def create_users(c):
    rows = c.d.get('users')
    if not isinstance(rows, list) or not rows or len(rows) > 500:
        raise E(400, '사용자 목록이 필요합니다.')
    out = []
    for d in rows:
        uid, pw = add_user(d)
        out.append({'id': uid, 'login': d['login'], 'password': pw})
    c.log('users_create', len(out))
    return {'created': out}


@route('PUT', r'/api/users/(\d+)', 'admin')
def update_user(c, uid):
    u = need(one('select * from users where id=?', (uid,)))
    role = c.d.get('role', u['role']); lang = c.d.get('lang', u['lang'])
    if role not in ROLES or lang not in LANGS:
        raise E(400, '값이 올바르지 않습니다.')
    active = 1 if c.d.get('active', u['active']) else 0
    if int(uid) == c.u['id'] and (not active or role != 'admin'):
        raise E(400, '자기 계정의 관리자 권한은 바꿀 수 없습니다.')
    email = check_email(c.d, int(uid)) if 'email' in c.d else u['email']
    if active:
        x('update users set pending=0 where id=?', (uid,))
    x('update users set name=?,role=?,dept=?,site=?,lang=?,active=?,email=?,sv=sv+? where id=?',
      (s(c.d, 'name', 80) or u['name'], role, c.d.get('dept', u['dept']), c.d.get('site', u['site']), lang, active, email, 0 if active else 1, uid))
    c.log('user_update', uid)
    return {'ok': True}


@route('POST', r'/api/users/(\d+)/reset', 'admin')
def reset_user(c, uid):
    need(one('select 1 x from users where id=?', (uid,)))
    pw = secrets.token_urlsafe(9); salt = secrets.token_hex(16)
    x('update users set salt=?,hash=?,must_change=1,sv=sv+1 where id=?', (salt, pw_hash(pw, salt), uid))
    c.log('user_reset', uid)
    return {'password': pw}


@route('DELETE', r'/api/me/links/(google|kakao|naver|sso)')
def unlink(c, k):
    if not c.u['hash'] and len(oauth.links(c.u['id'])) <= 1:
        raise E(400, '로그인 수단이 하나뿐이라 연결을 끊을 수 없습니다.')
    x('delete from oauth_links where provider=? and user_id=?', (k, c.u['id'])); c.log('unlink_' + k)
    return {'ok': True}


@route('GET', r'/api/settings/login', 'admin')
def login_settings(c):
    return oauth.settings()


@route('PUT', r'/api/settings/login', 'admin')
def login_settings_put(c):
    oauth.save(c.d); c.log('login_settings')
    return oauth.settings()


@route('GET', r'/api/audit', 'admin')
def audit(c):
    return {'rows': q('select a.*, u.name from audit a left join users u on u.id=a.user_id order by a.id desc limit 500')}


@route('GET', r'/api/audit\.xlsx', 'admin')
def audit_x(c):
    rows = q('select a.created,u.name,a.action,a.target,a.ip from audit a left join users u on u.id=a.user_id order by a.id desc limit 50000')
    return xlsx(c, 'audit', ['시각', '사용자', '행위', '대상', 'IP'], [list(r.values()) for r in rows])


# ---------- 매뉴얼·버전 ----------
def manual_row(m):
    v = one('select * from versions where id=?', (m['current_version'],)) if m['current_version'] else None
    m['version'] = v
    return m


@route('GET', r'/api/manuals')
def manuals(c):
    ms = q("select * from manuals where status!='archived' order by id desc") if role_ok(c.u, 'manager') else \
        [m for m in q("select * from manuals where status='published' order by id desc") if in_scope(c.u, m)]
    bm = {r['manual_id'] for r in q('select manual_id from bookmarks where user_id=?', (c.u['id'],))}
    for m in ms:
        m['bookmarked'] = m['id'] in bm
    return {'manuals': [manual_row(m) for m in ms]}


@route('POST', r'/api/manuals', 'manager')
def create_manual(c):
    kind = 'doc' if c.d.get('kind') == 'doc' else 'video'
    mid = x('insert into manuals(title,category,dept,owner_id,required,kind,tags) values(?,?,?,?,?,?,?)',
            (s(c.d, 'title', 200, True), s(c.d, 'category', 80), s(c.d, 'dept', 80), c.d.get('owner_id') or c.u['id'], 1 if c.d.get('required', True) else 0, kind, s(c.d, 'tags', 300)))
    if kind == 'doc':  # 문서 매뉴얼은 영상 없이 1판을 바로 만든다
        vid = x("insert into versions(manual_id,no,reason,author_id,state) values(?,1,'최초 등록',?,'ready')", (mid, c.u['id']))
        x('update manuals set current_version=? where id=?', (vid, mid))
    c.log('manual_create', mid)
    return {'id': mid}


def in_scope(u, m):
    if role_ok(u, 'manager') or not (m.get('scope') or '').strip():
        return True
    return u['dept'] in [d.strip() for d in m['scope'].split(',')] or bool(one('select 1 x from assigns where manual_id=? and user_id=?', (m['id'], u['id'])))


def can_see(c, m):
    if (m['status'] != 'published' or not in_scope(c.u, m)) and not role_ok(c.u, 'manager'):
        raise E(404, '찾을 수 없습니다.')


@route('GET', r'/api/manuals/(\d+)')
def manual(c, mid):
    m = need(one('select * from manuals where id=?', (mid,)))
    can_see(c, m)
    m = manual_row(m)
    m['versions'] = q('select v.*, u.name author from versions v left join users u on u.id=v.author_id where manual_id=? order by no desc', (mid,))
    m['steps'] = q('select * from steps where version_id=? order by ord', (m['current_version'] or 0,))
    m['sub_langs'] = [r['lang'] for r in q('select distinct lang from subs where version_id=? and confirmed=1', (m['current_version'] or 0,))]
    qz = q('select id,question,options,answer,step_ord from quiz where manual_id=? order by ord', (mid,))
    for z in qz:
        z['options'] = json.loads(z['options'])
        if not role_ok(c.u, 'manager'):
            z.pop('answer')
    m['quiz'] = qz
    m['owner'] = (one('select name from users where id=?', (m['owner_id'],)) or {}).get('name', '')
    v = one('select * from views where user_id=? and version_id=?', (c.u['id'], m['current_version'] or 0))
    m['my_pct'] = v['pct'] if v else 0
    m['my_done'] = bool(one('select 1 x from completions where user_id=? and version_id=?', (c.u['id'], m['current_version'] or 0)))
    m['bookmarked'] = bool(one('select 1 x from bookmarks where user_id=? and manual_id=?', (c.u['id'], mid)))
    m['narrations'] = [r['lang'] for r in q('select lang from narrations where version_id=? and not stale', (m['current_version'] or 0,))]
    tr = one('select title from manual_i18n where manual_id=? and lang=?', (mid, c.u['lang']))
    m['title_tr'] = tr['title'] if tr else ''
    m['step_langs'] = [r['lang'] for r in q('select distinct lang from step_i18n where version_id=?', (m['current_version'] or 0,))]
    m['approvals'] = q('select a.*,u.name from approvals a left join users u on u.id=a.approver_id where manual_id=? order by a.id desc, step limit 20', (mid,))
    c.log('manual_view', mid)
    return m


@route('PUT', r'/api/manuals/(\d+)', 'manager')
def update_manual(c, mid):
    m = need(one('select * from manuals where id=?', (mid,)))
    st = c.d.get('status', m['status'])
    if st not in ('draft', 'review', 'published', 'archived'):
        raise E(400, '상태 값이 올바르지 않습니다.')
    if st == 'published' and not m['current_version']:
        raise E(400, '처리가 끝난 영상이 있어야 공개할 수 있습니다.')
    owner = c.d.get('owner_id', m['owner_id'])
    if owner and not one('select 1 x from users where id=?', (owner,)):
        raise E(400, '담당자를 찾을 수 없습니다.')
    if st == 'published' and m['status'] != 'published' and one("select 1 x from approvals where manual_id=? and status='wait'", (mid,)):
        raise E(400, '승인 진행 중입니다. 승인이 끝나면 자동으로 공개됩니다.')
    if st == 'published' and m['status'] != 'published' and setting('approval_required') == '1':
        last = q("select status from approvals where manual_id=? and version_id=? and status!='cancel'", (mid, m['current_version']))
        if not last or any(a['status'] != 'ok' for a in last):
            raise E(400, '승인을 마친 버전만 공개할 수 있습니다. 승인을 요청하세요.')
    x('update manuals set title=?,category=?,dept=?,status=?,owner_id=?,required=?,tags=?,scope=? where id=?',
      (s(c.d, 'title', 200) or m['title'], c.d.get('category', m['category']), c.d.get('dept', m['dept']), st, owner,
       1 if c.d.get('required', m['required']) else 0, str(c.d.get('tags', m['tags']))[:300], str(c.d.get('scope', m['scope']))[:300], mid))
    c.log('manual_update', f'{mid}:{st}')
    return {'ok': True}


def probe(path):
    r = subprocess.run(['ffprobe', '-v', 'error', '-print_format', 'json', '-show_format', '-show_streams', path], capture_output=True, text=True, encoding='utf8', errors='replace', timeout=60)
    if r.returncode:
        return None
    j = json.loads(r.stdout)
    if not any(st.get('codec_type') == 'video' for st in j.get('streams', [])):
        return None
    return float(j.get('format', {}).get('duration') or 0)


def transcode(vid, src, mid):
    out = os.path.join(VIDEOS, f'{uuid.uuid4().hex}.mp4'); th = out[:-4] + '.jpg'
    try:
        r = subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', src, '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '24', '-pix_fmt', 'yuv420p',
                            '-vf', "scale=-2:'min(720,ih)':force_divisible_by=2", '-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart', out],
                           capture_output=True, text=True, encoding='utf8', errors='replace', timeout=4 * 3600)
        if r.returncode:
            raise RuntimeError(r.stderr[-300:])
        dur = probe(out) or 0
        subprocess.run(['ffmpeg', '-y', '-v', 'error', '-ss', str(min(1, dur / 2)), '-i', out, '-frames:v', '1', '-vf', 'scale=480:-2', th], capture_output=True, timeout=120)
        prev = one('select current_version c from manuals where id=?', (mid,))['c']

        def done(db):
            db.execute("update versions set file=?,thumb=?,duration=?,state='ready' where id=?", (os.path.basename(out), os.path.basename(th), dur, vid))
            if prev:  # 이전 버전 단계를 이어받는다
                for t in db.execute('select ord,start,end,title,note,warn,image from steps where version_id=?', (prev,)).fetchall():
                    db.execute('insert into steps(version_id,ord,start,end,title,note,warn,image) values(?,?,?,?,?,?,?,?)',
                               (vid, t['ord'], min(t['start'], dur), min(t['end'], dur), t['title'], t['note'], t['warn'], t['image']))
            db.execute('update manuals set current_version=? where id=?', (vid, mid))
            if prev and setting('approval_required') == '1':  # 개정본은 승인 뒤 배포
                db.execute("update manuals set status='review' where id=? and status='published'", (mid,))
        many(done)
    except Exception as ex:
        x("update versions set state='failed',error=? where id=?", (str(ex)[:300], vid))
    finally:
        if os.path.exists(src):
            os.remove(src)


@route('POST', r'/api/manuals/(\d+)/versions', 'manager', raw=True)
def upload(c, mid):
    h = c.h
    h.close_connection = True
    need(one('select 1 x from manuals where id=?', (mid,)))
    n = int(h.headers.get('Content-Length') or 0)
    if n <= 0 or n > MAX_VIDEO:
        raise E(413, f'영상은 {MAX_VIDEO // 1024 ** 2}MB 이하만 올릴 수 있습니다.')
    from urllib.parse import unquote
    reason = unquote(h.headers.get('X-Reason', ''))[:300].strip()
    prev = one('select max(no) n from versions where manual_id=?', (mid,))['n'] or 0
    if prev and not reason:
        raise E(400, '개정 사유를 입력하세요.')
    src = os.path.join(VIDEOS, f'{uuid.uuid4().hex}.src')
    with open(src, 'wb') as f:
        left = n
        while left:
            b = h.rfile.read(min(1 << 20, left))
            if not b:
                break
            f.write(b); left -= len(b)
    if left or not probe(src):
        os.remove(src)
        raise E(400, '영상 파일로 인식할 수 없습니다.')
    h.close_connection = False
    vid = x('insert into versions(manual_id,no,reason,author_id) values(?,?,?,?)', (mid, prev + 1, reason or '최초 등록', c.u['id']))
    threading.Thread(target=transcode, args=(vid, src, mid), daemon=True).start()
    for f in AFTER_UPLOAD:
        f(vid, c.u['id'], h.headers.get('X-Auto') == '1')
    c.log('version_upload', f'{mid}/{vid}')
    return {'version_id': vid}


def version(vid):
    return need(one('select * from versions where id=?', (vid,)))


def version_for(c, vid):
    v = version(vid)
    can_see(c, need(one('select * from manuals where id=?', (v['manual_id'],))))
    return v


@route('GET', r'/api/versions/(\d+)/video')
def video(c, vid):
    v = version_for(c, vid)
    if v['state'] != 'ready':
        raise E(409, '영상을 처리하는 중입니다.')
    p = os.path.join(VIDEOS, v['file']); size = os.path.getsize(p)
    m = re.match(r'bytes=(\d*)-(\d*)$', c.h.headers.get('Range', ''))
    start, end = 0, size - 1
    code = 200
    if m and (m[1] or m[2]):
        if m[1]:
            start = int(m[1]); end = min(int(m[2]), size - 1) if m[2] else size - 1
        else:
            start = max(0, size - int(m[2]))
        code = 206
        if start >= size or start > end:
            c.h.send(416, b'', 'video/mp4', extra=[('Content-Range', f'bytes */{size}')])
            return Done
    h = c.h
    h.send_response(code); h.send_header('Content-Type', 'video/mp4'); h.send_header('Accept-Ranges', 'bytes')
    h.send_header('Content-Length', str(end - start + 1)); h.send_header('Cache-Control', 'private, no-store')
    if code == 206:
        h.send_header('Content-Range', f'bytes {start}-{end}/{size}')
    h.end_headers()
    with open(p, 'rb') as f:
        f.seek(start); left = end - start + 1
        while left:
            b = f.read(min(1 << 18, left))
            if not b:
                break
            try:
                h.wfile.write(b)
            except OSError:
                break
            left -= len(b)
    return Done


@route('GET', r'/api/versions/(\d+)/thumb')
def thumb(c, vid):
    v = version_for(c, vid)
    p = os.path.join(VIDEOS, v['thumb'] or 'x')
    if not os.path.isfile(p):
        raise E(404, '없음')
    c.h.send(200, open(p, 'rb').read(), 'image/jpeg')
    return Done


@route('GET', r'/api/versions/(\d+)/status')
def v_status(c, vid):
    v = version_for(c, vid)
    return {'state': v['state'], 'error': v['error'], 'jobs': q('select lang,state,error from subjobs where version_id=?', (vid,))}


@route('PUT', r'/api/versions/(\d+)/steps', 'manager')
def put_steps(c, vid):
    v = version(vid); rows = c.d.get('steps')
    if not isinstance(rows, list) or len(rows) > 300:
        raise E(400, '단계 목록이 올바르지 않습니다.')
    clean = []
    doc = not v['file']
    for i, r in enumerate(rows):
        a, b = (0, 0) if doc else (fnum(r.get('start'), '시작'), fnum(r.get('end'), '끝'))
        if not doc and (a < 0 or b <= a or b > v['duration'] + 1):
            raise E(400, f'{i + 1}단계의 구간이 올바르지 않습니다.')
        img = str(r.get('image') or '')
        if img and not re.fullmatch(r'[0-9a-f]{32}\.(jpg|png|webp)', img):
            raise E(400, '그림 값이 올바르지 않습니다.')
        clean.append((vid, i, a, b, s(r, 'title', 200, True), s(r, 'note', 4000), s(r, 'warn', 500), img))

    for f in BEFORE_SAVE:
        f('steps', int(vid), c.u['id'])

    def w(db):
        db.execute('delete from steps where version_id=?', (vid,))
        db.executemany('insert into steps(version_id,ord,start,end,title,note,warn,image) values(?,?,?,?,?,?,?,?)', clean)
    many(w); c.log('steps_save', vid)
    return {'ok': True}


# ---------- AI 자막 ----------
def glossed(t):
    for g in q('select term,replace_with from glossary'):
        t = t.replace(g['term'], g['replace_with'])
    return t


def job(vid, lang, state, err=''):
    x('insert or replace into subjobs(version_id,lang,state,error) values(?,?,?,?)', (vid, lang, state, str(err)[:300]))


def asr_job(vid):
    v = version(vid); wav = os.path.join(VIDEOS, f'{uuid.uuid4().hex}.wav')
    try:
        src = os.path.join(VIDEOS, v['file'])
        r = subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', src, '-vn', '-af', 'highpass=f=80,lowpass=f=8000,afftdn=nf=-25,dynaudnorm', '-ac', '1', '-ar', '16000', wav], capture_output=True, text=True, encoding='utf8', errors='replace', timeout=1800)
        if r.returncode:
            raise RuntimeError('이 영상에는 소리가 없습니다.' if 'does not contain' in r.stderr or 'Output file' in r.stderr else r.stderr[-200:])
        r = subprocess.run([ASR_PY, '-X', 'utf8', os.path.join(BASE, 'asr_worker.py'), wav, 'ko'], capture_output=True, text=True, encoding='utf8', errors='replace', timeout=3 * 3600)
        if r.returncode:
            raise RuntimeError(r.stderr[-300:])
        segs = json.loads(r.stdout)

        def w(db):
            db.execute("delete from subs where version_id=? and lang='ko'", (vid,))
            db.executemany("insert into subs(version_id,lang,ord,start,end,text) values(?,'ko',?,?,?,?)", [(vid, i, g['start'], g['end'], glossed(g['text'])) for i, g in enumerate(segs)])
        many(w); job(vid, 'ko', 'done')
    except Exception as ex:
        job(vid, 'ko', 'failed', ex)
    finally:
        if os.path.exists(wav):
            os.remove(wav)


def ollama(prompt):
    body = json.dumps({'model': OLLAMA_MODEL, 'prompt': prompt, 'stream': False, 'think': False, 'keep_alive': os.environ.get('OLLAMA_KEEP_ALIVE', '24h'), 'options': {'temperature': 0}}, ensure_ascii=False).encode('utf8')
    r = urllib.request.urlopen(urllib.request.Request(OLLAMA + '/api/generate', body, {'Content-Type': 'application/json'}), timeout=300)
    return re.sub(r'<think>.*?</think>', '', json.load(r).get('response', ''), flags=re.S).strip()


def trans_job(vid, lang):
    try:
        src = q("select * from subs where version_id=? and lang='ko' order by ord", (vid,))
        rows = []
        for r in src:
            t = ollama(f'Translate this Korean workplace-safety subtitle into {LANGS[lang]}. Output only the translation, nothing else.\n\n{r["text"]}')
            rows.append((vid, lang, r['ord'], r['start'], r['end'], t.splitlines()[0] if t else ''))

        def w(db):
            db.execute('delete from subs where version_id=? and lang=?', (vid, lang))
            db.executemany('insert into subs(version_id,lang,ord,start,end,text) values(?,?,?,?,?,?)', rows)
        many(w); job(vid, lang, 'done')
    except Exception as ex:
        job(vid, lang, 'failed', ex)


@route('POST', r'/api/versions/(\d+)/subs/draft', 'manager')
def subs_draft(c, vid):
    if version(vid)['state'] != 'ready':
        raise E(409, '영상 처리가 끝난 뒤 실행하세요.')
    if not os.path.exists(ASR_PY):
        raise E(503, '받아쓰기 실행 환경이 없습니다. ASR_PYTHON 설정을 확인하세요.')
    job(vid, 'ko', 'running')
    threading.Thread(target=asr_job, args=(vid,), daemon=True).start()
    c.log('subs_draft', vid)
    return {'ok': True}


@route('POST', r'/api/versions/(\d+)/subs/translate', 'manager')
def subs_trans(c, vid):
    lang = c.d.get('lang')
    if lang not in LANGS or lang == 'ko':
        raise E(400, '언어가 올바르지 않습니다.')
    if not one("select 1 x from subs where version_id=? and lang='ko' and confirmed=1", (vid,)):
        raise E(400, '한국어 자막을 먼저 확정하세요.')
    job(vid, lang, 'running')
    threading.Thread(target=trans_job, args=(vid, lang), daemon=True).start()
    c.log('subs_translate', f'{vid}:{lang}')
    return {'ok': True}


@route('GET', r'/api/versions/(\d+)/subs')
def subs_get(c, vid):
    version_for(c, vid)
    return {'subs': q('select ord,start,end,text,confirmed from subs where version_id=? and lang=? order by ord', (vid, c.arg('lang', 'ko')))}


@route('PUT', r'/api/versions/(\d+)/subs', 'manager')
def subs_put(c, vid):
    v = version(vid); lang = c.d.get('lang'); rows = c.d.get('subs')
    if lang not in LANGS or not isinstance(rows, list) or len(rows) > 5000:
        raise E(400, '자막 값이 올바르지 않습니다.')
    conf = 1 if c.d.get('confirm') else 0
    clean = []
    for i, r in enumerate(rows):
        a, b = fnum(r.get('start'), '시작'), fnum(r.get('end'), '끝')
        if a < 0 or b <= a or b > v['duration'] + 1:
            raise E(400, f'{i + 1}번째 자막 시간이 올바르지 않습니다.')
        clean.append((vid, lang, i, a, b, s(r, 'text', 500, True), conf))

    for f in BEFORE_SAVE:
        f('subs:' + lang, int(vid), c.u['id'])

    def w(db):
        db.execute('delete from subs where version_id=? and lang=?', (vid, lang))
        db.executemany('insert into subs(version_id,lang,ord,start,end,text,confirmed) values(?,?,?,?,?,?,?)', clean)
        db.execute('update narrations set stale=1 where version_id=? and lang=?', (vid, lang))  # 자막이 바뀐 음성은 다시 만들 때까지 쓰지 않는다
    many(w); c.log('subs_save', f'{vid}:{lang}:{conf}')
    for f in AFTER_SUBS:  # 자막을 확정하면 그 언어의 읽기 음성도 다시 만든다(more.py)
        f(int(vid), lang, conf, c.u['id'])
    return {'ok': True}


def vtt_t(t):
    return time.strftime('%H:%M:%S', time.gmtime(int(t))) + f'.{int(t * 1000) % 1000:03d}'


@route('GET', r'/api/versions/(\d+)/subs\.vtt')
def subs_vtt(c, vid):
    version_for(c, vid)
    out = ['WEBVTT', '']
    for r in q('select start,end,text from subs where version_id=? and lang=? and confirmed=1 order by ord', (vid, c.arg('lang', 'ko'))):
        out += [f'{vtt_t(r["start"])} --> {vtt_t(r["end"])}', r['text'].replace('-->', '→'), '']
    c.h.send(200, '\n'.join(out).encode('utf8'), 'text/vtt; charset=utf-8')
    return Done


@route('GET', r'/api/glossary', 'manager')
def gloss(c):
    return {'rows': q('select * from glossary order by term')}


@route('POST', r'/api/glossary', 'manager')
def gloss_add(c):
    x('insert or replace into glossary(term,replace_with) values(?,?)', (s(c.d, 'term', 100, True), s(c.d, 'replace_with', 100, True)))
    return {'ok': True}


@route('DELETE', r'/api/glossary/(\d+)', 'manager')
def gloss_del(c, i):
    x('delete from glossary where id=?', (i,))
    return {'ok': True}


# ---------- 교육 배정·이수 ----------
def assign_to(mid, uids, due):
    many(lambda db: [db.execute('insert into assigns(manual_id,user_id,due) values(?,?,?) on conflict(manual_id,user_id) do update set due=excluded.due', (mid, u, due)) for u in uids])


def targets(d):
    """user_ids·부서·사업장 중 지정한 대상의 활성 사용자."""
    ids = {int(i) for i in d.get('user_ids') or []}
    for col in ('dept', 'site'):
        if d.get(col):
            ids |= {u['id'] for u in q(f'select id from users where active=1 and {col}=?', (str(d[col]),))}
    if d.get('all'):
        ids |= {u['id'] for u in q('select id from users where active=1')}
    if not ids:
        raise E(400, '대상을 선택하세요.')
    return [u['id'] for u in q(f"select id from users where active=1 and id in ({','.join('?' * len(ids))})", tuple(ids))]


@route('POST', r'/api/manuals/(\d+)/assign', 'manager')
def assign(c, mid):
    m = need(one('select * from manuals where id=?', (mid,)))
    if m['status'] != 'published':
        raise E(400, '공개한 매뉴얼만 배정할 수 있습니다.')
    u = targets(c.d); assign_to(mid, u, s(c.d, 'due', 10))
    c.log('assign', f'{mid}:{len(u)}')
    return {'assigned': len(u)}


def status_of(uid, m):  # ponytail: 사용자×매뉴얼마다 조회. 수천 명 규모면 completions 를 한 번에 읽어 묶는다
    """done / outdated(이전 버전 이수) / doing / todo"""
    cur = m['current_version']
    if cur and one('select 1 x from completions where user_id=? and version_id=?', (uid, cur)):
        return 'done'
    if one('select 1 x from completions where user_id=? and manual_id=?', (uid, m['id'])):
        return 'outdated'
    v = one('select pct from views where user_id=? and version_id=?', (uid, cur or 0))
    return 'doing' if v and v['pct'] > 0 else 'todo'


@route('GET', r'/api/my')
def my(c):
    rows = q("select a.due, m.* from assigns a join manuals m on m.id=a.manual_id where a.user_id=? and m.status='published' order by a.due='' , a.due", (c.u['id'],))
    for m in rows:
        manual_row(m); m['st'] = status_of(c.u['id'], m)
        v = one('select pct from views where user_id=? and version_id=?', (c.u['id'], m['current_version'] or 0))
        m['pct'] = v['pct'] if v else 0
    hist = q('select c.created,c.score,c.lang,m.title,v.no from completions c join manuals m on m.id=c.manual_id join versions v on v.id=c.version_id where c.user_id=? order by c.id desc', (c.u['id'],))
    return {'assigned': rows, 'history': hist}


@route('POST', r'/api/versions/(\d+)/progress')
def progress(c, vid):  # ponytail: 시청률은 브라우저 보고값. 서명·테스트로 보완하며, 강제가 필요하면 구간 토큰을 서버가 검증한다
    version_for(c, vid)
    pct = max(0.0, min(100.0, fnum(c.d.get('pct'), '시청률')))
    lang = c.d.get('lang') if c.d.get('lang') in LANGS else 'ko'
    x("insert into views(user_id,version_id,pct,lang,updated) values(?,?,?,?,datetime('now')) on conflict(user_id,version_id) do update set pct=max(pct,excluded.pct),lang=excluded.lang,updated=excluded.updated",
      (c.u['id'], vid, pct, lang))
    return {'ok': True}


@route('POST', r'/api/manuals/(\d+)/complete')
def complete(c, mid):
    m = need(one('select * from manuals where id=?', (mid,)))
    can_see(c, m)
    vid = m['current_version']
    if not vid:
        raise E(400, '영상이 없습니다.')
    v = one('select pct,lang from views where user_id=? and version_id=?', (c.u['id'], vid))
    if not v or v['pct'] < WATCH_MIN:
        raise E(400, f'영상을 {WATCH_MIN}% 이상 시청해야 합니다.')
    sig = str(c.d.get('signature', ''))
    if not sig.startswith('data:image/png;base64,') or len(sig) > 200_000:
        raise E(400, '서명이 필요합니다.')
    try:
        base64.b64decode(sig.split(',', 1)[1], validate=True)
    except Exception:
        raise E(400, '서명이 올바르지 않습니다.')
    qz = q('select id,answer,step_ord from quiz where manual_id=? order by ord', (mid,))
    ans = c.d.get('answers') or {}
    score = 100; by_step = {}
    for z in qz:
        k = 'all' if z['step_ord'] is None else str(z['step_ord'])
        by_step.setdefault(k, [0, 0]); by_step[k][1] += 1
        by_step[k][0] += str(ans.get(str(z['id']))) == str(z['answer'])
    steps = {k: round(100 * a / n) for k, (a, n) in by_step.items()}
    if qz:
        score = round(100 * sum(a for a, n in by_step.values()) / len(qz))
    x('insert into quiz_attempts(manual_id,version_id,user_id,score,passed,detail) values(?,?,?,?,?,?)',
      (mid, vid, c.u['id'], score, int(score >= PASS_SCORE), json.dumps({'steps': steps, 'answers': ans}, ensure_ascii=False)))
    if qz and score < PASS_SCORE:
        return {'passed': False, 'score': score, 'need': PASS_SCORE, 'steps': steps}
    x('insert or replace into completions(manual_id,version_id,user_id,score,lang,signature) values(?,?,?,?,?,?)', (mid, vid, c.u['id'], score, v['lang'], sig))
    dur = (one('select duration from versions where id=?', (vid,)) or {}).get('duration') or 0
    threading.Thread(target=send_edu, args=({'course': m['title'], 'minutes': max(1, round(dur / 60)), 'worker': c.u['name'], 'ref': f"{vid}:{c.u['id']}",
                                            'category': '영상 교육', 'completed_at': date.today().isoformat(), 'video_url': f'/app.html#/play/{mid}'},), daemon=True).start()
    c.log('complete', f'{mid}/{vid}')
    return {'passed': True, 'score': score, 'steps': steps}


@route('PUT', r'/api/manuals/(\d+)/quiz', 'manager')
def quiz_put(c, mid):
    need(one('select 1 x from manuals where id=?', (mid,)))
    rows = c.d.get('quiz')
    if not isinstance(rows, list) or len(rows) > 50:
        raise E(400, '문제 값이 올바르지 않습니다.')
    clean = []
    for i, r in enumerate(rows):
        opts = [str(o).strip()[:200] for o in (r.get('options') or []) if str(o).strip()]
        a = r.get('answer')
        if len(opts) < 2 or not isinstance(a, int) or not 0 <= a < len(opts):
            raise E(400, f'{i + 1}번 문제의 보기나 정답이 올바르지 않습니다.')
        so = r.get('step_ord')
        clean.append((mid, i, s(r, 'question', 500, True), json.dumps(opts, ensure_ascii=False), a, int(so) if isinstance(so, int) or str(so).isdigit() else None))

    def w(db):
        db.execute('delete from quiz where manual_id=?', (mid,))
        db.executemany('insert into quiz(manual_id,ord,question,options,answer,step_ord) values(?,?,?,?,?,?)', clean)
    many(w)
    return {'ok': True}


@route('GET', r'/api/courses')
def courses(c):
    cs = q('select * from courses order by id desc')
    for k in cs:
        k['items'] = q("select m.id,m.title,m.current_version,m.status from course_items i join manuals m on m.id=i.manual_id where i.course_id=? order by i.ord", (k['id'],))
        if not role_ok(c.u, 'manager'):
            k['items'] = [m for m in k['items'] if m['status'] == 'published' and in_scope(c.u, one('select * from manuals where id=?', (m['id'],)))]
        for m in k['items']:
            m['st'] = status_of(c.u['id'], m)
    return {'courses': cs if role_ok(c.u, 'manager') else [k for k in cs if k['items']]}


@route('POST', r'/api/courses', 'manager')
def course_new(c):
    ids = c.d.get('manual_ids') or []
    if not ids:
        raise E(400, '매뉴얼을 선택하세요.')
    cid = x('insert into courses(title) values(?)', (s(c.d, 'title', 200, True),))
    many(lambda db: [db.execute('insert into course_items values(?,?,?)', (cid, int(m), i)) for i, m in enumerate(ids)])
    return {'id': cid}


@route('POST', r'/api/courses/(\d+)/assign', 'manager')
def course_assign(c, cid):
    items = need(q("select m.id from course_items i join manuals m on m.id=i.manual_id where i.course_id=? and m.status='published'", (cid,)) or None, '공개된 매뉴얼이 없습니다.')
    u = targets(c.d)
    for m in items:
        assign_to(m['id'], u, s(c.d, 'due', 10))
    c.log('course_assign', f'{cid}:{len(u)}')
    return {'assigned': len(u), 'manuals': len(items)}


def matrix_data(dept=''):
    us = q('select id,name,dept,site,lang from users where active=1' + (' and dept=?' if dept else '') + ' order by dept,name', (dept,) if dept else ())
    ms = q("select * from manuals where status='published' order by id")
    asg = {(a['manual_id'], a['user_id']): a['due'] for a in q('select * from assigns')}
    cells = {}
    for u in us:
        for m in ms:
            st = status_of(u['id'], m)
            if (m['id'], u['id']) in asg or st == 'done':
                cells[f"{u['id']}:{m['id']}"] = {'st': st, 'due': asg.get((m['id'], u['id']), '')}
    return us, ms, cells


ST = {'done': '이수', 'outdated': '재이수 필요', 'doing': '진행 중', 'todo': '미이수'}


@route('GET', r'/api/matrix', 'manager')
def matrix(c):
    us, ms, cells = matrix_data(c.arg('dept'))
    capable = {m['id']: sum(1 for u in us if cells.get(f"{u['id']}:{m['id']}", {}).get('st') == 'done') for m in ms}
    return {'users': us, 'manuals': [{'id': m['id'], 'title': m['title']} for m in ms], 'cells': cells, 'capable': capable}


@route('GET', r'/api/matrix\.xlsx', 'manager')
def matrix_x(c):
    us, ms, cells = matrix_data(c.arg('dept'))
    rows = [[u['name'], u['dept'], u['site']] + [ST.get(cells.get(f"{u['id']}:{m['id']}", {}).get('st'), '-') for m in ms] for u in us]
    c.log('export_matrix')
    return xlsx(c, 'skill-matrix', ['이름', '부서', '사업장'] + [m['title'] for m in ms], rows)


def unfinished_rows():
    today = date.today().isoformat(); out = []
    for a in q("select a.due,u.id uid,u.name,u.dept,u.site,m.id,m.title,m.current_version from assigns a join users u on u.id=a.user_id join manuals m on m.id=a.manual_id where u.active=1 and m.status='published' order by a.due"):
        st = status_of(a['uid'], {'id': a['id'], 'current_version': a['current_version']})
        if st != 'done':
            out.append({'name': a['name'], 'dept': a['dept'], 'site': a['site'], 'title': a['title'], 'due': a['due'], 'st': ST[st], 'overdue': bool(a['due'] and a['due'] < today)})
    return out


@route('GET', r'/api/unfinished', 'manager')
def unfinished(c):
    return {'rows': unfinished_rows()}


@route('GET', r'/api/unfinished\.xlsx', 'manager')
def unfinished_x(c):
    c.log('export_unfinished')
    return xlsx(c, 'unfinished', ['이름', '부서', '사업장', '교육', '기한', '상태', '기한 경과'],
                [[r['name'], r['dept'], r['site'], r['title'], r['due'], r['st'], '예' if r['overdue'] else ''] for r in unfinished_rows()])


@route('GET', r'/api/completions\.xlsx', 'manager')
def comp_x(c):
    w, a = [], []
    if c.arg('from'):
        w.append('date(c.created)>=?'); a.append(c.arg('from'))
    if c.arg('to'):
        w.append('date(c.created)<=?'); a.append(c.arg('to'))
    rows = q('select c.created,u.name,u.dept,u.site,m.title,v.no,c.score,c.lang,case when c.signature is null then "" else "있음" end sign from completions c join users u on u.id=c.user_id join manuals m on m.id=c.manual_id join versions v on v.id=c.version_id'
             + (' where ' + ' and '.join(w) if w else '') + ' order by c.id desc', a)
    c.log('export_completions')
    return xlsx(c, 'education-records', ['이수 시각', '이름', '부서', '사업장', '교육', '버전', '점수', '언어', '서명'], [list(r.values()) for r in rows])


@route('GET', r'/api/completions', 'manager')
def comps(c):
    w, a = [], []
    if c.arg('from'):
        w.append('date(c.created)>=?'); a.append(c.arg('from'))
    if c.arg('to'):
        w.append('date(c.created)<=?'); a.append(c.arg('to'))
    return {'rows': q('select c.created,u.name,u.dept,u.site,m.title,v.no,c.score,c.lang,c.signature from completions c join users u on u.id=c.user_id join manuals m on m.id=c.manual_id join versions v on v.id=c.version_id'
                      + (' where ' + ' and '.join(w) if w else '') + ' order by c.id desc limit 2000', a)}


# ---------- 작업 분석 ----------
@route('GET', r'/api/compare', 'manager')
def compare_list(c):
    return {'versions': q("select v.id,v.no,v.duration,m.id manual_id,m.title,m.standard_version from versions v join manuals m on m.id=v.manual_id where v.state='ready' and m.status!='archived' order by m.title,v.no desc"),
            'notes': q('select n.*,u.name from compare_notes n left join users u on u.id=n.user_id where a_version=? and b_version=? order by t', (c.arg('a', '0'), c.arg('b', '0')))}


@route('POST', r'/api/compare/notes', 'manager')
def note_add(c):
    a, b = int(c.d.get('a') or 0), int(c.d.get('b') or 0)
    version(a); version(b)
    nid = x('insert into compare_notes(a_version,b_version,t,memo,user_id) values(?,?,?,?,?)', (a, b, max(0, fnum(c.d.get('t'), '시각')), s(c.d, 'memo', 1000, True), c.u['id']))
    return {'id': nid}


@route('POST', r'/api/manuals/(\d+)/standard', 'manager')
def standard(c, mid):
    vid = int(c.d.get('version_id') or 0)
    if not one('select 1 x from versions where id=? and manual_id=?', (vid, mid)):
        raise E(400, '이 매뉴얼의 버전이 아닙니다.')
    x('update manuals set standard_version=? where id=?', (vid, mid)); c.log('standard', f'{mid}/{vid}')
    return {'ok': True}


@route('GET', r'/api/tasks')
def tasks(c):
    w = '' if role_ok(c.u, 'manager') else ' where t.assignee_id=?'
    return {'tasks': q('select t.*,u.name assignee,m.title manual from tasks t left join users u on u.id=t.assignee_id left join manuals m on m.id=t.manual_id' + w + " order by t.status='done',t.due",
                       () if not w else (c.u['id'],))}


@route('POST', r'/api/tasks', 'manager')
def task_new(c):
    mid = c.d.get('manual_id') or None
    tid = x('insert into tasks(title,manual_id,assignee_id,due,note_id) values(?,?,?,?,?)', (s(c.d, 'title', 300, True), mid, c.d.get('assignee_id') or None, s(c.d, 'due', 10), c.d.get('note_id')))
    retrain = c.d.get('retrain_user_ids') or []
    if retrain and mid:
        m = need(one('select * from manuals where id=?', (mid,)))
        if m['status'] != 'published':
            raise E(400, '공개한 매뉴얼만 재교육을 배정할 수 있습니다.')
        assign_to(mid, targets({'user_ids': retrain}), s(c.d, 'due', 10))
    c.log('task_create', tid)
    return {'id': tid}


@route('PUT', r'/api/tasks/(\d+)')
def task_put(c, tid):
    t = need(one('select * from tasks where id=?', (tid,)))
    if not role_ok(c.u, 'manager') and t['assignee_id'] != c.u['id']:
        raise E(403, '권한이 없습니다.')
    if c.d.get('status') not in ('open', 'doing', 'done'):
        raise E(400, '상태 값이 올바르지 않습니다.')
    x('update tasks set status=? where id=?', (c.d['status'], tid))
    return {'ok': True}


# ---------- 점검표 ----------
@route('GET', r'/api/forms')
def forms(c):
    r = q('select * from forms where active=1 order by id desc')
    for f in r:
        f['schema'] = json.loads(f['schema'])
    return {'forms': r}


@route('POST', r'/api/forms', 'manager')
def form_new(c):
    items = c.d.get('schema')
    if not isinstance(items, list) or not items or len(items) > 100:
        raise E(400, '점검 항목이 필요합니다.')
    clean = []
    for i, it in enumerate(items):
        t = it.get('type')
        if t not in ('check', 'number', 'text'):
            raise E(400, f'{i + 1}번 항목 형식이 올바르지 않습니다.')
        o = {'label': s(it, 'label', 200, True), 'type': t}
        if t == 'number':
            for k in ('min', 'max'):
                if it.get(k) not in (None, ''):
                    o[k] = fnum(it[k], k)
            if 'min' in o and 'max' in o and o['min'] > o['max']:
                raise E(400, f'{i + 1}번 항목의 기준 범위가 올바르지 않습니다.')
        clean.append(o)
    fid = x('insert into forms(title,site,schema,owner_id) values(?,?,?,?)', (s(c.d, 'title', 200, True), s(c.d, 'site', 80), json.dumps(clean, ensure_ascii=False), c.u['id']))
    c.log('form_create', fid)
    return {'id': fid}


@route('DELETE', r'/api/forms/(\d+)', 'manager')
def form_del(c, fid):
    x('update forms set active=0 where id=?', (fid,))
    return {'ok': True}


@route('POST', r'/api/forms/(\d+)/submit')
def form_submit(c, fid):
    f = need(one('select * from forms where id=? and active=1', (fid,)))
    schema = json.loads(f['schema']); vals = c.d.get('values') or {}
    if not isinstance(vals, dict):
        raise E(400, '값이 올바르지 않습니다.')
    out, bad = [], []
    for i, it in enumerate(schema):
        v = vals.get(str(i))
        if it['type'] == 'check':
            v = bool(v)
            if not v:
                bad.append(f"{it['label']}: 불합격")
        elif it['type'] == 'number':
            if v in (None, ''):
                raise E(400, f"{it['label']} 값을 입력하세요.")
            v = fnum(v, it['label'])
            if ('min' in it and v < it['min']) or ('max' in it and v > it['max']):
                bad.append(f"{it['label']}: {v:g} (기준 {it.get('min', '')}~{it.get('max', '')})")
        else:
            v = str(v or '').strip()[:1000]
        out.append({'label': it['label'], 'value': v})
    sid = x('insert into submissions(form_id,user_id,vals,abnormal) values(?,?,?,?)', (fid, c.u['id'], json.dumps(out, ensure_ascii=False), 1 if bad else 0))
    if bad:
        x('insert into alerts(submission_id,message) values(?,?)', (sid, f"{f['title']} ({c.u['name']}): " + ', '.join(bad)))
    c.log('form_submit', fid)
    return {'id': sid, 'abnormal': bad}


def subs_query(fid, frm, to):
    w, a = ['s.form_id=?'], [fid]
    if frm:
        w.append('date(s.created)>=?'); a.append(frm)
    if to:
        w.append('date(s.created)<=?'); a.append(to)
    rows = q('select s.id,s.created,s.vals,s.abnormal,s.status,s.comment,u.name from submissions s left join users u on u.id=s.user_id where ' + ' and '.join(w) + ' order by s.id desc limit 5000', a)
    for r in rows:
        r['vals'] = json.loads(r['vals'])
    return rows


@route('GET', r'/api/forms/(\d+)/submissions', 'manager')
def form_subs(c, fid):
    return {'rows': subs_query(fid, c.arg('from'), c.arg('to'))}


@route('GET', r'/api/forms/(\d+)/report\.xlsx', 'manager')
def form_rep(c, fid):
    f = need(one('select * from forms where id=?', (fid,)))
    labels = [i['label'] for i in json.loads(f['schema'])]
    rows = [[r['created'], r['name'], '이상' if r['abnormal'] else '정상'] + [v['value'] if not isinstance(v['value'], bool) else ('합격' if v['value'] else '불합격') for v in r['vals']] for r in subs_query(fid, c.arg('from'), c.arg('to'))]
    c.log('export_form', fid)
    return xlsx(c, f'form-{fid}', ['제출 시각', '점검자', '판정'] + labels, rows)


@route('GET', r'/api/alerts', 'manager')
def alerts(c):
    return {'rows': q('select * from alerts order by done, id desc limit 200')}


@route('POST', r'/api/alerts/(\d+)/done', 'manager')
def alert_done(c, i):
    x('update alerts set done=1 where id=?', (i,))
    return {'ok': True}


# ---------- 중대재해 의무 관리 ----------
def cur_half():
    t = date.today()
    return f'{t.year}H{1 if t.month <= 6 else 2}'


def half_range(h):
    y, n = int(h[:4]), h[-1]
    return (f'{y}-01-01', f'{y}-06-30') if n == '1' else (f'{y}-07-01', f'{y}-12-31')


def edu_stats():
    total = done = 0
    for a in q("select a.user_id,m.id,m.current_version from assigns a join manuals m on m.id=a.manual_id join users u on u.id=a.user_id where m.status='published' and u.active=1"):
        total += 1
        if status_of(a['user_id'], {'id': a['id'], 'current_version': a['current_version']}) == 'done':
            done += 1
    return {'total': total, 'done': done}


def safety_rows(h):
    if not re.fullmatch(r'\d{4}H[12]', h):
        raise E(400, '반기 값이 올바르지 않습니다.')
    a, b = half_range(h)
    saved = {o['code']: o for o in q('select o.*,u.name by_name from obligations o left join users u on u.id=o.checked_by where half=?', (h,))}
    edu = edu_stats(); out = []
    for code, art, title, half, kind in LAW:
        o = saved.get(code, {})
        n = 0
        if kind and kind != 'edu':
            n = one('select count(*) n from records where kind=? and date(created) between ? and ?', (kind, a, b))['n']
        out.append({'code': code, 'article': art, 'title': title, 'half': half, 'kind': kind, 'status': o.get('status', 'todo'), 'memo': o.get('memo', ''),
                    'by': o.get('by_name', ''), 'at': o.get('checked_at', ''), 'evidence': edu if kind == 'edu' else n})
    return out


@route('GET', r'/api/safety', 'manager')
def safety(c):
    h = c.arg('half') or cur_half()
    rows = safety_rows(h)
    return {'half': h, 'rows': rows, 'done': sum(1 for r in rows if r['status'] == 'done'), 'total': len(rows), 'edu': edu_stats()}


@route('PUT', r'/api/safety/([0-9H]+)/(\d-\d)', 'manager')
def safety_put(c, h, code):
    safety_rows(h)
    if code not in {l[0] for l in LAW}:
        raise E(404, '항목이 없습니다.')
    st = c.d.get('status')
    if st not in ('todo', 'doing', 'done', 'na'):
        raise E(400, '상태 값이 올바르지 않습니다.')
    x("insert or replace into obligations(half,code,status,memo,checked_by,checked_at) values(?,?,?,?,?,datetime('now'))", (h, code, st, s(c.d, 'memo', 2000), c.u['id']))
    c.log('safety_update', f'{h}:{code}:{st}')
    return {'ok': True}


@route('GET', r'/api/safety/report\.xlsx', 'manager')
def safety_x(c):
    h = c.arg('half') or cur_half(); LBL = {'todo': '미착수', 'doing': '진행', 'done': '완료', 'na': '해당 없음'}
    rows = []
    for r in safety_rows(h):
        ev = f"{r['evidence']['done']}/{r['evidence']['total']} 이수" if r['kind'] == 'edu' else (f"{r['evidence']}건" if r['kind'] else '')
        rows.append([r['article'], r['title'], '반기 1회 이상' if r['half'] else '', LBL[r['status']], ev, r['memo'], r['by'], r['at']])
    c.log('export_safety', h)
    return xlsx(c, f'safety-{h}', ['근거 조문(시행령)', '의무', '점검 주기', '상태', '증빙', '메모', '점검자', '점검 시각'], rows)


@route('GET', r'/api/records')
def records(c):
    k = c.arg('kind')
    if k not in RECORD_KINDS:
        raise E(400, '종류가 올바르지 않습니다.')
    if not role_ok(c.u, 'manager') and k not in WORKER_KINDS:
        raise E(403, '권한이 없습니다.')
    w = '' if role_ok(c.u, 'manager') else ' and r.user_id=?'
    rows = q('select r.*,u.name from records r left join users u on u.id=r.user_id where r.kind=?' + w + ' order by r.id desc limit 500', (k,) if not w else (k, c.u['id']))
    for r in rows:
        r['data'] = json.loads(r['data'])
        if r['data'].get('anon') and not role_ok(c.u, 'admin'):
            r['name'] = '익명'
    return {'rows': rows}


@route('POST', r'/api/records')
def record_new(c):
    k = c.d.get('kind'); data = c.d.get('data')
    if k not in RECORD_KINDS or not isinstance(data, dict):
        raise E(400, '값이 올바르지 않습니다.')
    if not role_ok(c.u, 'manager') and k not in WORKER_KINDS:
        raise E(403, '권한이 없습니다.')
    clean = {str(a)[:40]: (b if isinstance(b, bool) else str(b)[:2000]) for a, b in list(data.items())[:20]}
    if not str(clean.get('title', '')).strip():
        raise E(400, '제목이 필요합니다.')
    rid = x('insert into records(kind,data,user_id) values(?,?,?)', (k, json.dumps(clean, ensure_ascii=False), c.u['id']))
    c.log('record_create', f'{k}:{rid}')
    return {'id': rid}


@route('PUT', r'/api/records/(\d+)', 'manager')
def record_put(c, rid):
    r = need(one('select * from records where id=?', (rid,)))
    if c.d.get('status') not in ('open', 'doing', 'done'):
        raise E(400, '상태 값이 올바르지 않습니다.')
    data = json.loads(r['data'])
    if 'action' in c.d:
        data['action'] = str(c.d['action'])[:2000]
    x('update records set status=?,data=? where id=?', (c.d['status'], json.dumps(data, ensure_ascii=False), rid))
    c.log('record_update', rid)
    return {'ok': True}


@route('GET', r'/api/dashboard', 'manager')
def dash(c):
    e = edu_stats(); h = cur_half(); rows = safety_rows(h)
    return {'edu': e, 'half': h, 'safety_done': sum(1 for r in rows if r['status'] in ('done', 'na')), 'safety_total': len(rows),
            'manuals': one("select count(*) n from manuals where status='published'")['n'], 'users': one('select count(*) n from users where active=1')['n'],
            'alerts': one('select count(*) n from alerts where done=0')['n'], 'hazards': one("select count(*) n from records where kind='hazard' and status!='done'")['n'],
            'tasks': one("select count(*) n from tasks where status!='done'")['n'], 'overdue': sum(1 for r in unfinished_rows() if r['overdue'])}
