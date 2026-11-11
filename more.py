"""원본 서비스 기능 대조로 추가한 API: 즐겨찾기·작성 계획·다단 승인·문서 매뉴얼 그림·매뉴얼 리포트, 스킬 평가·자기평가·교육 계획,
AI 골자 작성·단계 자동 분할·자막 읽기 음성·음성 교체, 요소 작업 분해·비교 설명, 점검 결과 승인, 2단계 인증, 백업."""
import base64, hashlib, hmac, io, json, os, re, secrets, shutil, sqlite3, struct, subprocess, sys, threading, time, uuid
from datetime import date

import product as P
from product import route, E, Done, s, need, fnum, role_ok, xlsx, LANGS, version, version_for, can_see, job, ollama, VIDEOS, status_of, assign_to, targets
from db import DATA, DB, LOCK, one, q, x, many

IMG = re.compile(r'[0-9a-f]{32}\.(jpg|png|webp)')
VOICES = {'ko': 'ko-KR-SunHiNeural', 'en': 'en-US-AnaNeural', 'vi': 'vi-VN-HoaiMyNeural', 'zh': 'zh-CN-XiaoxiaoNeural', 'th': 'th-TH-NiwatNeural',
          'ne': 'ne-NP-HemkalaNeural', 'id': 'id-ID-ArdiNeural', 'uz': 'uz-UZ-MadinaNeural', 'ja': 'ja-JP-KeitaNeural', 'km': 'km-KH-PisethNeural',
          'mn': 'mn-MN-BataaNeural', 'my': 'my-MM-NilarNeural', 'ru': 'ru-RU-DmitryNeural', 'fil': 'fil-PH-AngeloNeural', 'bn': 'bn-BD-NabanitaNeural',
          'ur': 'ur-PK-AsadNeural', 'si': 'si-LK-SameeraNeural', 'lo': 'lo-LA-ChanthavongNeural', 'kk': 'kk-KZ-AigulNeural', 'hi': 'hi-IN-MadhurNeural',
          'ar': 'ar-SA-HamedNeural', 'es': 'es-ES-AlvaroNeural', 'fr': 'fr-FR-DeniseNeural', 'de': 'de-DE-AmalaNeural', 'pt': 'pt-BR-AntonioNeural',
          'tr': 'tr-TR-AhmetNeural', 'uk': 'uk-UA-OstapNeural'}


def raw_body(c, limit):
    h = c.h; h.close_connection = True
    n = int(h.headers.get('Content-Length') or 0)
    if n <= 0 or n > limit:
        raise E(413, '파일이 너무 큽니다.')
    b = h.rfile.read(n)
    h.close_connection = False
    return b


# ---------- 즐겨찾기 ----------
@route('POST', r'/api/manuals/(\d+)/bookmark')
def bookmark(c, mid):
    m = need(one('select * from manuals where id=?', (mid,))); can_see(c, m)
    if c.d.get('on'):
        x('insert or ignore into bookmarks(user_id,manual_id) values(?,?)', (c.u['id'], mid))
    else:
        x('delete from bookmarks where user_id=? and manual_id=?', (c.u['id'], mid))
    return {'ok': True}


# ---------- 문서 매뉴얼 그림 ----------
@route('POST', r'/api/images', 'manager', raw=True)
def image_up(c):
    b = raw_body(c, 10 * 1024 * 1024)
    ext = 'png' if b[:8] == b'\x89PNG\r\n\x1a\n' else 'jpg' if b[:3] == b'\xff\xd8\xff' else 'webp' if b[8:12] == b'WEBP' else None
    if not ext:
        raise E(400, 'JPG·PNG·WEBP 그림만 올릴 수 있습니다.')
    name = f'{uuid.uuid4().hex}.{ext}'
    open(os.path.join(VIDEOS, name), 'wb').write(b)
    return {'image': name}


@route('GET', r'/api/images/([0-9a-f]{32}\.(?:jpg|png|webp))')
def image_get(c, name):
    p = os.path.join(VIDEOS, name)
    if not os.path.isfile(p):
        raise E(404, '없음')
    if not role_ok(c.u, 'manager'):  # 근로자는 볼 수 있는 매뉴얼에 쓰인 그림만
        ok = any(m['status'] == 'published' and P.in_scope(c.u, m) for m in q('select distinct m.* from steps s join versions v on v.id=s.version_id join manuals m on m.id=v.manual_id where s.image=?', (name,)))
        if not ok:
            raise E(404, '없음')
    c.h.send(200, open(p, 'rb').read(), {'jpg': 'image/jpeg', 'png': 'image/png', 'webp': 'image/webp'}[name.rsplit('.', 1)[1]])
    return Done


@route('POST', r'/api/manuals/(\d+)/docversion', 'manager')
def doc_version(c, mid):
    m = need(one("select * from manuals where id=? and kind='doc'", (mid,)))
    reason = s(c.d, 'reason', 300, True)
    prev = m['current_version']; no = one('select max(no) n from versions where manual_id=?', (mid,))['n'] or 0

    def w(db):
        vid = db.execute("insert into versions(manual_id,no,reason,author_id,state) values(?,?,?,?,'ready')", (mid, no + 1, reason, c.u['id'])).lastrowid
        db.execute('insert into steps(version_id,ord,start,end,title,note,warn,image) select ?,ord,start,end,title,note,warn,image from steps where version_id=?', (vid, prev))
        db.execute('update manuals set current_version=? where id=?', (vid, mid))
        if P.setting('approval_required') == '1':
            db.execute("update manuals set status='review' where id=? and status='published'", (mid,))
        return vid
    vid = many(w); c.log('doc_version', f'{mid}/{vid}')
    return {'version_id': vid}


# ---------- 매뉴얼 리포트 ----------
@route('GET', r'/api/manuals/(\d+)/report', 'manager')
def report(c, mid):
    m = need(one('select * from manuals where id=?', (mid,)))
    rows = []
    for a in q('select a.due,u.id,u.name,u.dept from assigns a join users u on u.id=a.user_id where a.manual_id=? order by u.dept,u.name', (mid,)):
        v = one('select pct from views where user_id=? and version_id=?', (a['id'], m['current_version'] or 0))
        cp = one('select score,created from completions where user_id=? and manual_id=? order by id desc limit 1', (a['id'], mid))
        rows.append({'name': a['name'], 'dept': a['dept'], 'due': a['due'], 'st': status_of(a['id'], m), 'pct': round(v['pct']) if v else 0,
                     'score': cp['score'] if cp else None, 'at': cp['created'] if cp else ''})
    views = one('select count(*) n, avg(pct) p from views where version_id=?', (m['current_version'] or 0,))
    return {'rows': rows, 'viewers': views['n'], 'avg_pct': round(views['p'] or 0), 'done': sum(1 for r in rows if r['st'] == 'done'), 'total': len(rows)}


# ---------- 작성 계획 ----------
@route('GET', r'/api/plans', 'manager')
def plans(c):
    return {'rows': q('select p.*,u.name owner,m.title manual from plans p left join users u on u.id=p.owner_id left join manuals m on m.id=p.manual_id order by p.status="done", p.due')}


@route('POST', r'/api/plans', 'manager')
def plan_new(c):
    pid = x('insert into plans(title,owner_id,due,manual_id) values(?,?,?,?)', (s(c.d, 'title', 200, True), c.d.get('owner_id') or None, s(c.d, 'due', 10), c.d.get('manual_id') or None))
    return {'id': pid}


@route('PUT', r'/api/plans/(\d+)', 'manager')
def plan_put(c, pid):
    p = need(one('select * from plans where id=?', (pid,)))
    st = c.d.get('status', p['status'])
    if st not in ('todo', 'doing', 'done'):
        raise E(400, '상태 값이 올바르지 않습니다.')
    x('update plans set status=?,manual_id=?,owner_id=?,due=? where id=?', (st, c.d.get('manual_id', p['manual_id']) or None, c.d.get('owner_id', p['owner_id']) or None, str(c.d.get('due', p['due']))[:10], pid))
    return {'ok': True}


# ---------- 다단 승인 ----------
@route('POST', r'/api/manuals/(\d+)/approval', 'manager')
def approval_req(c, mid):
    m = need(one('select * from manuals where id=?', (mid,)))
    if not m['current_version']:
        raise E(400, '내용이 있어야 승인을 요청할 수 있습니다.')
    ids = [int(i) for i in c.d.get('approver_ids') or []]
    if not ids or len(ids) > 5 or len(set(ids)) != len(ids):
        raise E(400, '승인자를 1~5명 순서대로 고르세요.')
    for i in ids:
        u = one('select * from users where id=? and active=1', (i,))
        if not u or not role_ok(u, 'manager'):
            raise E(400, '승인자는 관리자 권한이 있어야 합니다.')

    def w(db):
        db.execute("update approvals set status='cancel' where manual_id=? and status='wait'", (mid,))
        for n, i in enumerate(ids):
            db.execute('insert into approvals(manual_id,step,approver_id,requested_by,version_id) values(?,?,?,?,?)', (mid, n, i, c.u['id'], m['current_version']))
        db.execute("update manuals set status='review' where id=?", (mid,))
    many(w); c.log('approval_request', mid)
    return {'ok': True}


@route('GET', r'/api/approvals', 'manager')
def my_approvals(c):
    rows = q("select a.*,m.title,u.name requester from approvals a join manuals m on m.id=a.manual_id left join users u on u.id=a.requested_by where a.status='wait' and a.approver_id=? order by a.id", (c.u['id'],))
    # 내 차례인 것만: 앞 단계가 모두 승인됨
    return {'rows': [r for r in rows if not one("select 1 x from approvals where manual_id=? and step<? and status='wait'", (r['manual_id'], r['step']))]}


@route('POST', r'/api/approvals/(\d+)', 'manager')
def approve(c, aid):
    a = need(one("select * from approvals where id=? and status='wait'", (aid,)))
    if a['approver_id'] != c.u['id']:
        raise E(403, '내 승인 차례가 아닙니다.')
    if one("select 1 x from approvals where manual_id=? and step<? and status='wait'", (a['manual_id'], a['step'])):
        raise E(400, '앞 단계 승인이 끝나지 않았습니다.')
    ok = bool(c.d.get('ok'))

    def w(db):
        db.execute("update approvals set status=?,comment=?,at=datetime('now') where id=?", ('ok' if ok else 'reject', s(c.d, 'comment', 1000), aid))
        if not ok:
            db.execute("update approvals set status='cancel' where manual_id=? and status='wait'", (a['manual_id'],))
            db.execute("update manuals set status='draft' where id=?", (a['manual_id'],))
        elif not db.execute("select 1 from approvals where manual_id=? and status='wait'", (a['manual_id'],)).fetchone():
            cur = db.execute('select current_version from manuals where id=?', (a['manual_id'],)).fetchone()[0]
            if a['version_id'] in (None, cur):  # 승인받은 버전이 지금 버전일 때만 공개
                db.execute("update manuals set status='published' where id=?", (a['manual_id'],))
    many(w); c.log('approval_' + ('ok' if ok else 'reject'), a['manual_id'])
    return {'ok': True, 'published': bool(one("select 1 x from manuals where id=? and status='published'", (a['manual_id'],)))}


# ---------- 스킬 ----------
LEVELS = ['미교육', '교육 중', '지도 하에 가능', '혼자 가능', '지도 가능']


@route('GET', r'/api/skills')
def skills(c):
    rows = q('select * from skills order by category, name')
    for r in rows:
        r['manual_ids'] = json.loads(r['manual_ids'])
    return {'skills': rows, 'levels': LEVELS}


@route('POST', r'/api/skills', 'manager')
def skill_new(c):
    ids = [int(i) for i in c.d.get('manual_ids') or []]
    sid = x('insert into skills(name,category,manual_ids) values(?,?,?)', (s(c.d, 'name', 120, True), s(c.d, 'category', 80), json.dumps(ids)))
    return {'id': sid}


def lvl(v):
    try:
        v = int(v)
    except (TypeError, ValueError):
        raise E(400, '수준 값이 올바르지 않습니다.')
    if not 0 <= v < len(LEVELS):
        raise E(400, '수준 값이 올바르지 않습니다.')
    return v


@route('POST', r'/api/skills/eval', 'manager')
def skill_eval(c):
    uid, sid = int(c.d.get('user_id') or 0), int(c.d.get('skill_id') or 0)
    need(one('select 1 x from users where id=?', (uid,))); need(one('select 1 x from skills where id=?', (sid,)))
    x("insert into evals(user_id,skill_id,level,kind,evaluator_id,comment) values(?,?,?,'eval',?,?)", (uid, sid, lvl(c.d.get('level')), c.u['id'], s(c.d, 'comment', 1000)))
    c.log('skill_eval', f'{uid}:{sid}')
    return {'ok': True}


@route('POST', r'/api/skills/self')
def skill_self(c):
    sid = int(c.d.get('skill_id') or 0); need(one('select 1 x from skills where id=?', (sid,)))
    x("insert into evals(user_id,skill_id,level,kind,evaluator_id,comment) values(?,?,?,'self',?,?)", (c.u['id'], sid, lvl(c.d.get('level')), c.u['id'], s(c.d, 'comment', 1000)))
    return {'ok': True}


@route('POST', r'/api/skills/plan', 'manager')
def skill_plan(c):
    sid = int(c.d.get('skill_id') or 0); need(one('select 1 x from skills where id=?', (sid,)))
    t = lvl(c.d.get('target')); due = s(c.d, 'due', 10, True); us = targets(c.d)
    many(lambda db: [db.execute('insert into skill_plans(user_id,skill_id,target,due) values(?,?,?,?) on conflict(user_id,skill_id) do update set target=excluded.target,due=excluded.due', (u, sid, t, due)) for u in us])
    return {'planned': len(us)}


def latest(uid, sid, kind):
    r = one('select level,created from evals where user_id=? and skill_id=? and kind=? order by id desc limit 1', (uid, sid, kind))
    return r


def skill_cells(dept=''):
    us = q('select id,name,dept from users where active=1' + (' and dept=?' if dept else '') + ' order by dept,name', (dept,) if dept else ())
    sk = q('select * from skills order by category,name'); today = date.today().isoformat(); cells = {}
    for u in us:
        for k in sk:
            e, se = latest(u['id'], k['id'], 'eval'), latest(u['id'], k['id'], 'self')
            p = one('select target,due from skill_plans where user_id=? and skill_id=?', (u['id'], k['id']))
            if e or se or p:
                lv = e['level'] if e else 0
                cells[f"{u['id']}:{k['id']}"] = {'level': lv, 'self': se['level'] if se else None, 'target': p['target'] if p else None, 'due': p['due'] if p else '',
                                                  'late': bool(p and p['due'] < today and lv < p['target'])}
    return us, sk, cells


@route('GET', r'/api/skills/matrix', 'manager')
def skill_matrix(c):
    us, sk, cells = skill_cells(c.arg('dept'))
    return {'users': us, 'skills': [{'id': k['id'], 'name': k['name'], 'category': k['category']} for k in sk], 'cells': cells, 'levels': LEVELS,
            'milestones': q('select p.due,p.target,u.name,k.name skill from skill_plans p join users u on u.id=p.user_id join skills k on k.id=p.skill_id where u.active=1 order by p.due')}


@route('GET', r'/api/skills/matrix\.xlsx', 'manager')
def skill_matrix_x(c):
    us, sk, cells = skill_cells(c.arg('dept'))
    f = lambda cl: '-' if not cl else f"{LEVELS[cl['level']]}" + (f" (목표 {LEVELS[cl['target']]} {cl['due']})" if cl['target'] is not None else '')
    return xlsx(c, 'skill-map', ['이름', '부서'] + [k['name'] for k in sk], [[u['name'], u['dept']] + [f(cells.get(f"{u['id']}:{k['id']}")) for k in sk] for u in us])


@route('GET', r'/api/skills/me')
def skill_me(c):
    return skill_person(c, c.u['id'])


@route('GET', r'/api/skills/user/(\d+)', 'manager')
def skill_user(c, uid):
    return skill_person(c, int(uid))


def skill_person(c, uid):
    u = need(one('select id,name,dept from users where id=?', (uid,)))
    out = []
    for k in q('select * from skills order by category,name'):
        ms = json.loads(k['manual_ids'])
        edu = q(f"select m.title,c.created,c.score from completions c join manuals m on m.id=c.manual_id where c.user_id=? and c.manual_id in ({','.join('?' * len(ms)) or 'null'}) order by c.id desc", (uid, *ms))
        hist = q('select e.level,e.kind,e.comment,e.created,v.name by_name from evals e left join users v on v.id=e.evaluator_id where e.user_id=? and e.skill_id=? order by e.id desc', (uid, k['id']))
        p = one('select target,due from skill_plans where user_id=? and skill_id=?', (uid, k['id']))
        out.append({'id': k['id'], 'name': k['name'], 'category': k['category'], 'education': edu, 'history': hist, 'plan': p})
    return {'user': u, 'skills': out, 'levels': LEVELS}


# ---------- AI: 문서→골자, 자막→단계, 읽기 음성 ----------
def extract_text(b):
    if b[:4] == b'%PDF':
        from pypdf import PdfReader
        return '\n'.join((pg.extract_text() or '') for pg in PdfReader(io.BytesIO(b)).pages[:40])
    if b[:2] == b'PK':
        import docx
        return '\n'.join(p.text for p in docx.Document(io.BytesIO(b)).paragraphs)
    try:
        return b.decode('utf-8')
    except UnicodeDecodeError:
        return b.decode('cp949', errors='replace')


def json_list(t):
    m = re.search(r'\[.*\]', t, re.S)
    try:
        v = json.loads(m.group(0)) if m else []
    except ValueError:
        v = []
    return [d for d in v if isinstance(d, dict) and str(d.get('title', '')).strip()][:40]


@route('POST', r'/api/ai/outline', 'manager', raw=True)
def outline(c):
    text = extract_text(raw_body(c, 20 * 1024 * 1024)).strip()
    if len(text) < 20:
        raise E(400, '문서에서 글을 읽지 못했습니다. 글자가 있는 PDF·Word·텍스트 파일을 올리세요.')
    try:
        r = ollama('다음 작업 절차서를 현장 교육용 매뉴얼 단계로 나눠라. JSON 배열만 출력하라. 각 항목은 {"title": 짧은 단계 제목, "note": 해야 할 일 설명, "warn": 안전 주의사항(없으면 빈 문자열)}. 원문에 없는 내용은 만들지 마라.\n\n' + text[:6000])
    except Exception:
        raise E(503, 'AI 실행 환경(Ollama)에 연결하지 못했습니다.')
    steps = [{'title': str(d['title'])[:200], 'note': str(d.get('note', ''))[:2000], 'warn': str(d.get('warn', ''))[:500]} for d in json_list(r)]
    if not steps:
        raise E(502, 'AI가 단계를 만들지 못했습니다. 다시 시도하세요.')
    c.log('ai_outline', len(steps))
    return {'steps': steps}


@route('POST', r'/api/versions/(\d+)/autosteps', 'manager')
def autosteps(c, vid):
    return {'steps': make_autosteps(vid)}


def make_autosteps(vid):
    v = version(vid)
    subs = q("select start,end,text from subs where version_id=? and lang='ko' order by ord", (vid,))
    if not subs:
        raise E(400, '한국어 자막(받아쓰기)이 먼저 있어야 합니다.')
    lines = '\n'.join(f"{i}: [{r['start']:.1f}-{r['end']:.1f}] {r['text']}" for i, r in enumerate(subs))
    try:
        r = ollama('아래는 작업 영상의 자막 줄이다. 연속된 줄을 묶어 작업 단계로 나눠라. JSON 배열만 출력하라. 각 항목은 {"from": 시작 줄 번호, "to": 끝 줄 번호, "title": 짧은 단계 제목, "note": 그 단계에서 작업자가 할 일을 한두 문장으로 쓴 안내, "warn": 안전 주의사항 또는 빈 문자열}. 자막에 없는 내용은 만들지 마라.\n\n' + lines[:6000])
    except Exception:
        raise E(503, 'AI 실행 환경(Ollama)에 연결하지 못했습니다.')
    out = []
    for d in json_list(r):
        try:
            a, b = max(0, int(d.get('from', 0))), min(len(subs) - 1, int(d.get('to', 0)))
        except (TypeError, ValueError):
            continue
        if a <= b:
            out.append({'start': subs[a]['start'], 'end': min(subs[b]['end'], v['duration']), 'title': str(d['title'])[:200], 'note': (str(d.get('note') or '').strip() or ' '.join(x['text'] for x in subs[a:b + 1]))[:2000], 'warn': str(d.get('warn', ''))[:500]})
    if not out:
        out = [{'start': r['start'], 'end': r['end'], 'title': r['text'][:40], 'note': r['text'], 'warn': ''} for r in subs]
    return out


_VOICE_LIST = []


def voices_for(lang):
    if not _VOICE_LIST:
        p = subprocess.run([sys.executable, '-m', 'edge_tts', '--list-voices'], capture_output=True, text=True, encoding='utf8', errors='replace', timeout=60)
        _VOICE_LIST.extend(l.split()[0] for l in p.stdout.splitlines() if 'Neural' in l)
    loc = VOICES[lang].rsplit('-', 1)[0]
    return [v for v in _VOICE_LIST if v.startswith(loc + '-')]


def tts_job(vid, lang, replace, uid):
    key = 'tts-' + lang
    tmp = os.path.join(VIDEOS, uuid.uuid4().hex); os.makedirs(tmp)
    try:
        rows = q('select start,end,text from subs where version_id=? and lang=? and confirmed=1 order by ord', (vid, lang))
        v = version(vid); inputs, filt = [], []
        for i, r in enumerate(rows):
            f = os.path.join(tmp, f'{i}.mp3')
            for attempt, voice in enumerate([VOICES[lang]] * 3 + [v for v in voices_for(lang) if v != VOICES[lang]][:2] * 2):  # 서비스가 간헐적으로 빈 응답을 주면 다시, 그래도 안 되면 같은 언어 다른 목소리
                p = subprocess.run([sys.executable, '-m', 'edge_tts', '--voice', voice, '--text', r['text'], '--write-media', f], capture_output=True, timeout=120)
                if not p.returncode and os.path.exists(f) and os.path.getsize(f) > 0:
                    break
                time.sleep(1 + attempt)
            else:
                raise RuntimeError('음성 합성 서비스가 응답하지 않았습니다. 잠시 뒤 다시 시도하세요.')
            inputs += ['-i', f]; filt.append(f'[{i}:a]adelay={int(r["start"] * 1000)}|{int(r["start"] * 1000)}[a{i}]')
        out = os.path.join(VIDEOS, f'{uuid.uuid4().hex}.m4a')
        mix = ';'.join(filt) + ';' + ''.join(f'[a{i}]' for i in range(len(rows))) + f'amix=inputs={len(rows)}:normalize=0,apad,atrim=0:{v["duration"]:.2f}[out]'
        p = subprocess.run(['ffmpeg', '-y', '-v', 'error', *inputs, '-filter_complex', mix, '-map', '[out]', '-c:a', 'aac', out], capture_output=True, text=True, encoding='utf8', errors='replace', timeout=1800)
        if p.returncode:
            raise RuntimeError(p.stderr[-200:])
        x('insert or replace into narrations(version_id,lang,file) values(?,?,?)', (vid, lang, os.path.basename(out)))
        if replace:  # 영상 음성을 읽기 음성으로 바꾼 새 버전
            nv = os.path.join(VIDEOS, f'{uuid.uuid4().hex}.mp4')
            p = subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', os.path.join(VIDEOS, v['file']), '-i', out, '-map', '0:v', '-map', '1:a', '-c:v', 'copy', '-c:a', 'aac', '-shortest', '-movflags', '+faststart', nv],
                               capture_output=True, text=True, encoding='utf8', errors='replace', timeout=1800)
            if p.returncode:
                raise RuntimeError(p.stderr[-200:])
            no = one('select max(no) n from versions where manual_id=?', (v['manual_id'],))['n']

            def w(db):
                nid = db.execute("insert into versions(manual_id,no,file,thumb,reason,author_id,state,duration) values(?,?,?,?,?,?,'ready',?)",
                                 (v['manual_id'], no + 1, os.path.basename(nv), v['thumb'], f'영상 음성을 AI 읽기({LANGS[lang]})로 교체', uid, v['duration'])).lastrowid
                db.execute('insert into steps(version_id,ord,start,end,title,note,warn,image) select ?,ord,start,end,title,note,warn,image from steps where version_id=?', (nid, vid))
                db.execute('insert into subs(version_id,lang,ord,start,end,text,confirmed) select ?,lang,ord,start,end,text,confirmed from subs where version_id=?', (nid, vid))
                db.execute('update manuals set current_version=? where id=?', (nid, v['manual_id']))
            many(w)
        job(vid, key, 'done')
    except Exception as ex:
        job(vid, key, 'failed', ex)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@route('POST', r'/api/versions/(\d+)/tts', 'manager')
def tts(c, vid):
    v = version(vid); lang = c.d.get('lang')
    if not (lang in VOICES or P.voice_for(lang)) or not v['file']:
        raise E(400, '언어가 올바르지 않습니다.')
    if not one('select 1 x from subs where version_id=? and lang=? and confirmed=1', (vid, lang)):
        raise E(400, '이 언어의 확정된 자막이 있어야 합니다.')
    job(vid, 'tts-' + lang, 'running')
    threading.Thread(target=tts_job, args=(int(vid), lang, bool(c.d.get('replace')), c.u['id']), daemon=True).start()
    c.log('tts', f'{vid}:{lang}')
    return {'ok': True}


@route('GET', r'/api/versions/(\d+)/narration')
def narration(c, vid):
    version_for(c, vid)
    r = need(one('select file from narrations where version_id=? and lang=?', (vid, c.arg('lang', 'ko'))))
    c.h.send(200, open(os.path.join(VIDEOS, r['file']), 'rb').read(), 'audio/mp4')
    return Done


# ---------- 요소 작업 분해·비교 ----------
def split_job(vid):
    try:
        v = version(vid); src = os.path.join(VIDEOS, v['file']); dur = v['duration']
        p = subprocess.run(['ffmpeg', '-v', 'info', '-i', src, '-vf', 'scdet=threshold=8', '-an', '-f', 'null', '-'], capture_output=True, text=True, encoding='utf8', errors='replace', timeout=3600)
        cuts = sorted({round(float(t), 2) for t in re.findall(r'lavfi\.scd\.time:\s*([\d.]+)', p.stderr) if 1 < float(t) < dur - 1})
        bounds, last = [0.0], 0.0
        for t in cuts + [dur]:  # 장면 전환 기준, 10초를 넘으면 쪼개고 2초 미만은 붙인다
            while t - last > 10:
                last += 10; bounds.append(round(last, 2))
            if t - last >= 2 or t == dur:
                bounds.append(t); last = t
        if bounds[-1] != dur:
            bounds.append(dur)
        subs = q("select start,end,text from subs where version_id=? and lang='ko' order by ord", (vid,))
        rows = []
        for i in range(len(bounds) - 1):
            a, b = bounds[i], bounds[i + 1]
            if b - a < 0.5:
                continue
            said = ' '.join(r['text'] for r in subs if r['start'] < b and r['end'] > a)
            rows.append((vid, len(rows), a, b, (said[:40] or f'요소 {len(rows) + 1}')))

        def w(db):
            db.execute('delete from elements where version_id=?', (vid,))
            db.executemany('insert into elements(version_id,ord,start,end,label) values(?,?,?,?,?)', rows)
        many(w); job(vid, 'split', 'done')
    except Exception as ex:
        job(vid, 'split', 'failed', ex)


@route('POST', r'/api/versions/(\d+)/elements', 'manager')
def elements_make(c, vid):
    if version(vid)['state'] != 'ready' or not version(vid)['file']:
        raise E(400, '처리된 영상이 필요합니다.')
    job(vid, 'split', 'running'); threading.Thread(target=split_job, args=(int(vid),), daemon=True).start()
    return {'ok': True}


@route('GET', r'/api/versions/(\d+)/elements', 'manager')
def elements(c, vid):
    return {'rows': q('select ord,start,end,label from elements where version_id=? order by ord', (vid,)), 'duration': version(vid)['duration']}


@route('PUT', r'/api/versions/(\d+)/elements', 'manager')
def elements_put(c, vid):
    v = version(vid); rows = c.d.get('rows')
    if not isinstance(rows, list) or len(rows) > 500:
        raise E(400, '값이 올바르지 않습니다.')
    clean = []
    for i, r in enumerate(rows):
        a, b = fnum(r.get('start')), fnum(r.get('end'))
        if a < 0 or b <= a or b > v['duration'] + 1:
            raise E(400, f'{i + 1}번 요소 구간이 올바르지 않습니다.')
        clean.append((vid, i, a, b, s(r, 'label', 100)))

    def w(db):
        db.execute('delete from elements where version_id=?', (vid,))
        db.executemany('insert into elements(version_id,ord,start,end,label) values(?,?,?,?,?)', clean)
    many(w)
    return {'ok': True}


@route('POST', r'/api/compare/explain', 'manager')
def explain(c):
    a, b = int(c.d.get('a') or 0), int(c.d.get('b') or 0)
    ea = q('select ord,start,end,label from elements where version_id=? order by ord', (a,)); eb = q('select ord,start,end,label from elements where version_id=? order by ord', (b,))
    if not ea or not eb:
        raise E(400, '두 영상 모두 요소 작업 분해를 먼저 하세요.')
    n = min(len(ea), len(eb)); diffs = []
    for i in range(n):
        da, db_ = ea[i]['end'] - ea[i]['start'], eb[i]['end'] - eb[i]['start']
        diffs.append({'ord': i, 'a': round(da, 1), 'b': round(db_, 1), 'diff': round(db_ - da, 1), 'label': ea[i]['label']})
    ta, tb = ea[-1]['end'], eb[-1]['end']
    facts = f"기준 영상 총 {ta:.1f}초 요소 {len(ea)}개, 비교 영상 총 {tb:.1f}초 요소 {len(eb)}개.\n" + '\n'.join(f"요소{d['ord'] + 1}({d['label']}): 기준 {d['a']}초, 비교 {d['b']}초, 차이 {d['diff']:+}초" for d in diffs)
    try:
        text = ollama('아래 수치만 근거로, 비교 영상이 기준 영상과 어디서 얼마나 차이 나는지 현장 관리자에게 3~5문장 한국어로 설명하라. 수치에 없는 원인은 추정이라고 밝혀라.\n\n' + facts)
    except Exception:
        text = ''
    worst = sorted(diffs, key=lambda d: -abs(d['diff']))[:3]
    return {'diffs': diffs, 'total': {'a': round(ta, 1), 'b': round(tb, 1)}, 'text': text, 'worst': worst}


# ---------- 점검 결과 승인 ----------
@route('POST', r'/api/submissions/(\d+)/review', 'manager')
def sub_review(c, sid):
    need(one('select 1 x from submissions where id=?', (sid,)))
    st = 'ok' if c.d.get('ok') else 'reject'
    x('update submissions set status=?,approver_id=?,comment=? where id=?', (st, c.u['id'], s(c.d, 'comment', 500), sid))
    c.log('submission_' + st, sid)
    return {'ok': True}


# ---------- 2단계 인증(TOTP) ----------
def totp(key, t=None, step=0):
    k = base64.b32decode(key + '=' * (-len(key) % 8))
    m = hmac.new(k, struct.pack('>Q', int((t or time.time()) // 30) + step), hashlib.sha1).digest()
    o = m[-1] & 15
    return f"{(struct.unpack('>I', m[o:o + 4])[0] & 0x7fffffff) % 1000000:06d}"


def totp_ok(key, code):
    code = re.sub(r'\D', '', str(code or ''))
    return len(code) == 6 and any(hmac.compare_digest(totp(key, step=d), code) for d in (-1, 0, 1))


PENDING_TOTP = {}


@route('POST', r'/api/me/2fa/setup')
def tfa_setup(c):
    key = base64.b32encode(secrets.token_bytes(20)).decode().rstrip('=')
    PENDING_TOTP[c.u['id']] = key
    from urllib.parse import quote
    return {'key': key, 'uri': f"otpauth://totp/{quote('세이프업:' + c.u['login'])}?secret={key}&issuer={quote('세이프업')}"}


@route('POST', r'/api/me/2fa/enable')
def tfa_enable(c):
    key = PENDING_TOTP.get(c.u['id'])
    if not key or not totp_ok(key, c.d.get('code')):
        raise E(400, '인증 코드가 맞지 않습니다.')
    x('update users set totp=? where id=?', (key, c.u['id'])); PENDING_TOTP.pop(c.u['id'], None); c.log('2fa_on')
    return {'ok': True}


@route('POST', r'/api/me/2fa/disable')
def tfa_disable(c):
    if not c.u['totp'] or not totp_ok(c.u['totp'], c.d.get('code')):
        raise E(400, '인증 코드가 맞지 않습니다.')
    x("update users set totp='' where id=?", (c.u['id'],)); c.log('2fa_off')
    return {'ok': True}


@route('POST', r'/api/users/(\d+)/2fa-reset', 'admin')
def tfa_reset(c, uid):
    x("update users set totp='' where id=?", (uid,)); c.log('2fa_reset', uid)
    return {'ok': True}


# ---------- 접속 IP 제한·백업 ----------
def setting(k, default=''):
    r = one('select v from settings where k=?', (k,))
    return r['v'] if r else default


def ip_allowed(ip):
    import ipaddress
    rules = [r.strip() for r in setting('allowed_ips').split(',') if r.strip()]
    if not rules:
        return True
    try:
        a = ipaddress.ip_address(ip)
        return any(a in ipaddress.ip_network(r, strict=False) for r in rules)
    except ValueError:
        return False


@route('GET', r'/api/settings/security', 'admin')
def sec_get(c):
    return {'allowed_ips': setting('allowed_ips'), 'my_ip': c.h.ip(), 'backups': sorted(os.listdir(BACKUPS))[-14:]}


@route('PUT', r'/api/settings/security', 'admin')
def sec_put(c):
    import ipaddress
    v = ','.join(r.strip() for r in str(c.d.get('allowed_ips', '')).split(',') if r.strip())
    for r in v.split(',') if v else []:
        try:
            ipaddress.ip_network(r, strict=False)
        except ValueError:
            raise E(400, f'IP 형식이 올바르지 않습니다: {r}')
    x('insert or replace into settings(k,v) values(?,?)', ('allowed_ips', v))
    if not ip_allowed(c.h.ip()):
        x('insert or replace into settings(k,v) values(?,?)', ('allowed_ips', ''))
        raise E(400, f'지금 접속한 IP({c.h.ip()})가 목록에 없어 저장하지 않았습니다.')
    c.log('ip_rules', v)
    return {'ok': True}


BACKUPS = os.path.join(DATA, 'backups'); os.makedirs(BACKUPS, exist_ok=True)


def backup_now():
    name = os.path.join(BACKUPS, f'app-{time.strftime("%Y%m%d-%H%M%S")}.db')
    with LOCK:
        dst = sqlite3.connect(name); DB.backup(dst); dst.close()
    for old in sorted(os.listdir(BACKUPS))[:-14]:
        os.remove(os.path.join(BACKUPS, old))
    return name


def backup_loop():
    while True:
        try:
            if not any(f.startswith('app-' + time.strftime('%Y%m%d')) for f in os.listdir(BACKUPS)):
                backup_now()
        except Exception as ex:
            print('backup', ex)
        time.sleep(3600)


@route('POST', r'/api/backup', 'admin')
def backup(c):
    name = backup_now(); c.log('backup', os.path.basename(name))
    c.h.send(200, open(name, 'rb').read(), 'application/octet-stream', extra=[('Content-Disposition', f'attachment; filename="{os.path.basename(name)}"')])
    return Done



# ---------- 자막 확정 시 읽기 음성 자동 갱신 ----------
def _refresh_tts(vid, lang, conf, uid):
    if conf and (lang in VOICES or P.voice_for(lang)) and one('select 1 x from narrations where version_id=? and lang=?', (vid, lang)):
        job(vid, 'tts-' + lang, 'running')
        threading.Thread(target=tts_job, args=(vid, lang, False, uid), daemon=True).start()


P.AFTER_SUBS.append(_refresh_tts)


# ---------- 도형·강조 표시 ----------
DB.execute('create table if not exists annotations(id integer primary key, version_id int, start real, end real, kind text, x real, y real, w real, h real, color text, text text)')
DB.commit()
SHAPES = {'circle', 'rect', 'arrow', 'text'}


@route('GET', r'/api/versions/(\d+)/annotations')
def ann_get(c, vid):
    version_for(c, vid)
    return {'rows': q('select start,end,kind,x,y,w,h,color,text from annotations where version_id=? order by start', (vid,))}


@route('PUT', r'/api/versions/(\d+)/annotations', 'manager')
def ann_put(c, vid):
    v = version(vid); rows = c.d.get('rows')
    if not isinstance(rows, list) or len(rows) > 300:
        raise E(400, '값이 올바르지 않습니다.')
    clean = []
    for i, r in enumerate(rows):
        a, b = fnum(r.get('start')), fnum(r.get('end'))
        geo = [fnum(r.get(k)) for k in ('x', 'y', 'w', 'h')]
        if r.get('kind') not in SHAPES or a < 0 or b <= a or b > v['duration'] + 1 or not all(-1 <= g <= 2 for g in geo):
            raise E(400, f'{i + 1}번 표시가 올바르지 않습니다.')
        color = str(r.get('color') or '#e8531b')
        if not re.fullmatch(r'#[0-9a-fA-F]{6}', color):
            raise E(400, '색 값이 올바르지 않습니다.')
        clean.append((vid, a, b, r['kind'], *geo, color, s(r, 'text', 100)))

    for f in P.BEFORE_SAVE:
        f('annotations', int(vid), c.u['id'])

    def w(db):
        db.execute('delete from annotations where version_id=?', (vid,))
        db.executemany('insert into annotations(version_id,start,end,kind,x,y,w,h,color,text) values(?,?,?,?,?,?,?,?,?,?)', clean)
    many(w)
    return {'ok': True}


# ---------- 설명 음성 덮어쓰기(녹음) → 새 버전 + 자막 자동 생성 ----------
@route('POST', r'/api/versions/(\d+)/voiceover', 'manager', raw=True)
def voiceover(c, vid):
    v = version(vid)
    if not v['file']:
        raise E(400, '영상 매뉴얼에서만 쓸 수 있습니다.')
    b = raw_body(c, P.MAX_VIDEO)
    src = os.path.join(VIDEOS, uuid.uuid4().hex + '.rec'); open(src, 'wb').write(b)
    out = os.path.join(VIDEOS, uuid.uuid4().hex + '.mp4')
    try:
        p = subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', os.path.join(VIDEOS, v['file']), '-i', src, '-map', '0:v', '-map', '1:a', '-c:v', 'copy', '-c:a', 'aac',
                            '-af', f'apad,atrim=0:{v["duration"]:.2f}', '-t', f'{v["duration"]:.2f}', '-movflags', '+faststart', out], capture_output=True, text=True, encoding='utf8', errors='replace', timeout=1800)
        if p.returncode:
            raise E(400, '녹음 파일을 처리하지 못했습니다.')
    finally:
        os.remove(src)
    no = one('select max(no) n from versions where manual_id=?', (v['manual_id'],))['n']

    def w(db):
        nid = db.execute("insert into versions(manual_id,no,file,thumb,reason,author_id,state,duration) values(?,?,?,?,?,?,'ready',?)",
                         (v['manual_id'], no + 1, os.path.basename(out), v['thumb'], '설명 음성 녹음으로 교체', c.u['id'], v['duration'])).lastrowid
        db.execute('insert into steps(version_id,ord,start,end,title,note,warn,image) select ?,ord,start,end,title,note,warn,image from steps where version_id=?', (nid, vid))
        db.execute('insert into annotations(version_id,start,end,kind,x,y,w,h,color,text) select ?,start,end,kind,x,y,w,h,color,text from annotations where version_id=?', (nid, vid))
        db.execute('update manuals set current_version=? where id=?', (nid, v['manual_id']))
        return nid
    nid = many(w)
    if os.path.exists(P.ASR_PY):  # 녹음한 설명에서 자막을 바로 만든다
        job(nid, 'ko', 'running'); threading.Thread(target=P.asr_job, args=(nid,), daemon=True).start()
    c.log('voiceover', f"{v['manual_id']}/{nid}")
    return {'version_id': nid, 'asr': os.path.exists(P.ASR_PY)}


# ---------- 영상 내려받기 ----------
@route('GET', r'/api/versions/(\d+)/download', 'manager')
def download(c, vid):
    v = version(vid)
    if not v['file']:
        raise E(404, '영상이 없습니다.')
    m = one('select title from manuals where id=?', (v['manual_id'],))
    from urllib.parse import quote
    c.h.send(200, open(os.path.join(VIDEOS, v['file']), 'rb').read(), 'video/mp4', extra=[('Content-Disposition', f"attachment; filename*=UTF-8''{quote(m['title'])}-v{v['no']}.mp4")])
    c.log('video_download', vid)
    return Done


# ---------- 기한 알림 ----------
def notices_for(uid):
    today = date.today(); out = []
    for a in q("select a.due,m.id,m.title,m.current_version from assigns a join manuals m on m.id=a.manual_id where a.user_id=? and a.due!='' and m.status='published'", (uid,)):
        if status_of(uid, {'id': a['id'], 'current_version': a['current_version']}) == 'done':
            continue
        left = (date.fromisoformat(a['due']) - today).days
        if left <= 3:
            out.append({'kind': 'edu', 'id': a['id'], 'title': a['title'], 'due': a['due'], 'left': left})
    for t in q("select id,title,due from tasks where assignee_id=? and status!='done' and due!=''", (uid,)):
        left = (date.fromisoformat(t['due']) - today).days
        if left <= 3:
            out.append({'kind': 'task', 'id': t['id'], 'title': t['title'], 'due': t['due'], 'left': left})
    return sorted(out, key=lambda r: r['left'])


@route('GET', r'/api/notices')
def notices(c):
    return {'rows': notices_for(c.u['id'])}


def mail_loop():
    """SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_FROM 과 비밀번호 환경변수가 있으면 하루 한 번 기한 알림 메일을 보낸다."""
    import smtplib
    from email.message import EmailMessage
    DB.execute('create table if not exists notice_log(user_id int, day text, primary key(user_id, day))'); DB.commit()
    while True:
        try:
            if os.environ.get('SMTP_HOST'):
                day = date.today().isoformat()
                for u in q("select id,name,email from users where active=1 and email!=''"):
                    rows = notices_for(u['id'])
                    if not rows or one('select 1 x from notice_log where user_id=? and day=?', (u['id'], day)):
                        continue
                    msg = EmailMessage(); msg['Subject'] = f'[세이프업] 기한이 다가온 교육·과제 {len(rows)}건'
                    msg['From'] = os.environ.get('SMTP_FROM') or os.environ.get('SMTP_USER'); msg['To'] = u['email']
                    msg.set_content(f"{u['name']}님,\n\n" + '\n'.join(f"- {r['title']} (기한 {r['due']}, {'지남' if r['left'] < 0 else str(r['left']) + '일 남음'})" for r in rows))
                    with smtplib.SMTP(os.environ['SMTP_HOST'], int(os.environ.get('SMTP_PORT', 587)), timeout=20) as sm:
                        sm.starttls()
                        if os.environ.get('SMTP_USER'):
                            sm.login(os.environ['SMTP_USER'], os.environ.get('SMTP_' + 'PASSWORD', ''))
                        sm.send_message(msg)
                    x('insert into notice_log(user_id,day) values(?,?)', (u['id'], day))
        except Exception as ex:
            print('mail', ex)
        time.sleep(3600)


# ---------- 활용 현황 ----------
@route('GET', r'/api/usage', 'manager')
def usage(c):
    rows = q("""select m.id,m.title,m.kind,m.status,
                 (select count(*) from views v where v.version_id=m.current_version) viewers,
                 (select round(avg(pct)) from views v where v.version_id=m.current_version) avg_pct,
                 (select count(*) from completions x where x.manual_id=m.id) completions,
                 (select count(*) from assigns a where a.manual_id=m.id) assigned,
                 (select max(updated) from views v where v.version_id=m.current_version) last_view
               from manuals m where m.status!='archived' order by viewers desc, completions desc""")
    logins = q("select date(created) day, count(distinct user_id) users, count(*) n from audit where action like 'login%' and action not like '%fail' and created >= date('now','-30 day') group by day order by day")
    views = q("select date(created) day, count(*) n from audit where action='manual_view' and created >= date('now','-30 day') group by day order by day")
    return {'manuals': rows, 'logins': logins, 'views': views}


# ---------- AI: 기존 점검표 PDF·문서에서 점검 항목 가져오기 ----------
@route('POST', r'/api/ai/checklist', 'manager', raw=True)
def checklist_ai(c):
    text = extract_text(raw_body(c, 20 * 1024 * 1024)).strip()
    if len(text) < 20:
        raise E(400, '문서에서 글을 읽지 못했습니다. 글자가 있는 PDF·Word·텍스트 파일을 올리세요.')
    # 번호 붙은 질문형 항목(예: '1. 보호구를 착용하였는가?')이 있으면 원문 그대로 바로 쓴다. 없을 때만 AI
    found = list(dict.fromkeys(m.strip() for m in re.findall(r'(?:^|\s)\d{1,2}[.)]\s*([^?\n]{4,150}\?)', text)))
    if len(found) >= 3:
        return {'items': [{'label': f[:200], 'type': 'check'} for f in found[:100]], 'by': 'rule'}
    try:
        r = ollama('다음 문서에서 현장 점검 항목만 뽑아라. JSON 배열만 출력하라. 각 항목은 {"title": 점검 항목 문장, "type": "check"(양호/미흡 판정) 또는 "number"(수치 측정) 또는 "text"(기록)}. 원문에 있는 항목만, 원문 문장 그대로.\n\n' + text[:6000])
    except Exception:
        raise E(503, 'AI 실행 환경(Ollama)에 연결하지 못했습니다.')
    items = [{'label': str(d['title'])[:200], 'type': d.get('type') if d.get('type') in ('check', 'number', 'text') else 'check'} for d in json_list(r)]
    if not items:
        raise E(502, 'AI가 항목을 찾지 못했습니다. 다시 시도하세요.')
    return {'items': items}
