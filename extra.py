"""원작 서비스 기능 체크리스트 외부 채점(코덱스 2026-11-09)에서 빠지거나 부분이던 기능.
100개 언어·문서 글 번역, 개정 이력·되돌리기, 단계별 확인 테스트 기록, 폴더 분류, 과정 편집·진행 리포트, PDF→매뉴얼·과정 자동 생성,
업로드 후 자막·단계 자동, 자막·도형을 입힌 영상 내보내기, 승인 필수 배포, 사용자별 세부 권한, 조직 SSO, 도입 지원(목표·계획·정기 점검), 보고서."""
import io, json, os, re, subprocess, threading, uuid
from datetime import date

import product as P
import more as M
from product import route, E, Done, s, need, fnum, role_ok, version, version_for, can_see, job, ollama, VIDEOS
from db import DB, one, q, x, many

DB.executescript('''
create table if not exists step_i18n(version_id int, ord int, lang text, title text, note text, warn text, primary key(version_id, ord, lang));
create table if not exists manual_i18n(manual_id int, lang text, title text, primary key(manual_id, lang));
create table if not exists revisions(id integer primary key, version_id int, kind text, data text, user_id int, created text default current_timestamp);
create table if not exists quiz_attempts(id integer primary key, manual_id int, version_id int, user_id int, score int, passed int, detail text, created text default current_timestamp);
create table if not exists folders(id integer primary key, parent_id int, name text not null, ord int default 0);
create table if not exists exports(version_id int, lang text, file text, primary key(version_id, lang));
create table if not exists ob_goals(id integer primary key, title text, metric text, target text, current text default '', due text default '', owner_id int, created text default current_timestamp);
create table if not exists ob_plan(id integer primary key, week int, title text, priority text default '중', status text default 'todo', owner_id int, note text default '');
create table if not exists ob_meetings(id integer primary key, day text, kind text, attendees text, notes text, actions text default '', created_by int, created text default current_timestamp);
''')
for t, col, decl in [('manuals', 'folder_id', 'int'), ('quiz', 'step_ord', 'int'), ('approvals', 'version_id', 'int'), ('narrations', 'stale', 'int default 0'),
                     ('users', 'perms', "text default ''")]:
    if col not in [r[1] for r in DB.execute(f'pragma table_info({t})').fetchall()]:
        DB.execute(f'alter table {t} add column {col} {decl}')
DB.commit()

# ---------- 100개 이상 언어 ----------
MORE_LANGS = {
    'af': 'Afrikaans', 'am': 'አማርኛ', 'az': 'Azərbaycan', 'be': 'Беларуская', 'bg': 'Български', 'bs': 'Bosanski', 'ca': 'Català', 'ceb': 'Cebuano',
    'cs': 'Čeština', 'cy': 'Cymraeg', 'da': 'Dansk', 'el': 'Ελληνικά', 'eo': 'Esperanto', 'et': 'Eesti', 'eu': 'Euskara', 'fa': 'فارسی', 'fi': 'Suomi',
    'ga': 'Gaeilge', 'gl': 'Galego', 'gu': 'ગુજરાતી', 'ha': 'Hausa', 'haw': 'ʻŌlelo Hawaiʻi', 'he': 'עברית', 'hmn': 'Hmoob', 'hr': 'Hrvatski',
    'ht': 'Kreyòl ayisyen', 'hu': 'Magyar', 'hy': 'Հայերեն', 'ig': 'Igbo', 'is': 'Íslenska', 'it': 'Italiano', 'jv': 'Basa Jawa', 'ka': 'ქართული',
    'kn': 'ಕನ್ನಡ', 'ku': 'Kurdî', 'ky': 'Кыргызча', 'la': 'Latina', 'lb': 'Lëtzebuergesch', 'lt': 'Lietuvių', 'lv': 'Latviešu', 'mg': 'Malagasy',
    'mi': 'Māori', 'mk': 'Македонски', 'ml': 'മലയാളം', 'mr': 'मराठी', 'ms': 'Bahasa Melayu', 'mt': 'Malti', 'nl': 'Nederlands', 'no': 'Norsk',
    'ny': 'Chichewa', 'or': 'ଓଡ଼ିଆ', 'pa': 'ਪੰਜਾਬੀ', 'pl': 'Polski', 'ps': 'پښتو', 'ro': 'Română', 'rw': 'Kinyarwanda', 'sd': 'سنڌي', 'sk': 'Slovenčina',
    'sl': 'Slovenščina', 'sm': 'Gagana Samoa', 'sn': 'chiShona', 'so': 'Soomaali', 'sq': 'Shqip', 'sr': 'Српски', 'st': 'Sesotho', 'su': 'Basa Sunda',
    'sv': 'Svenska', 'sw': 'Kiswahili', 'ta': 'தமிழ்', 'te': 'తెలుగు', 'tg': 'Тоҷикӣ', 'tk': 'Türkmen', 'tt': 'Татар', 'ug': 'ئۇيغۇرچە', 'xh': 'isiXhosa',
    'yi': 'ייִדיש', 'yo': 'Yorùbá', 'zu': 'isiZulu', 'zh-TW': '繁體中文', 'fy': 'Frysk', 'gd': 'Gàidhlig', 'co': 'Corsu', 'ln': 'Lingála',
    'qu': 'Runa Simi', 'ti': 'ትግርኛ', 'om': 'Afaan Oromoo', 'ak': 'Akan', 'ee': 'Eʋegbe', 'lg': 'Luganda', 'as': 'অসমীয়া', 'dv': 'ދިވެހި', 'gn': 'Avañeʼẽ',
    'ilo': 'Ilokano', 'kri': 'Krio', 'mai': 'मैथिली', 'mni': 'ꯃꯩꯇꯩꯂꯣꯟ', 'sa': 'संस्कृतम्', 'ts': 'Xitsonga', 'bho': 'भोजपुरी', 'doi': 'डोगरी',
    'ckb': 'کوردیی ناوەندی', 'lus': 'Mizo ṭawng', 'nso': 'Sepedi', 'tw': 'Twi', 'ber': 'Tamaziɣt'}
P.LANGS.update({k: v for k, v in MORE_LANGS.items() if k not in P.LANGS})
LOCALES = {'af': 'af-ZA', 'am': 'am-ET', 'az': 'az-AZ', 'bg': 'bg-BG', 'bs': 'bs-BA', 'ca': 'ca-ES', 'cs': 'cs-CZ', 'cy': 'cy-GB', 'da': 'da-DK', 'el': 'el-GR',
           'et': 'et-EE', 'eu': 'eu-ES', 'fa': 'fa-IR', 'fi': 'fi-FI', 'ga': 'ga-IE', 'gl': 'gl-ES', 'gu': 'gu-IN', 'he': 'he-IL', 'hr': 'hr-HR', 'hu': 'hu-HU',
           'hy': 'hy-AM', 'is': 'is-IS', 'it': 'it-IT', 'jv': 'jv-ID', 'ka': 'ka-GE', 'kn': 'kn-IN', 'lt': 'lt-LT', 'lv': 'lv-LV', 'mk': 'mk-MK', 'ml': 'ml-IN',
           'mr': 'mr-IN', 'ms': 'ms-MY', 'mt': 'mt-MT', 'nl': 'nl-NL', 'no': 'nb-NO', 'pa': 'pa-IN', 'pl': 'pl-PL', 'ps': 'ps-AF', 'ro': 'ro-RO', 'sk': 'sk-SK',
           'sl': 'sl-SI', 'so': 'so-SO', 'sq': 'sq-AL', 'sr': 'sr-RS', 'su': 'su-ID', 'sv': 'sv-SE', 'sw': 'sw-KE', 'ta': 'ta-IN', 'te': 'te-IN', 'zu': 'zu-ZA',
           'zh-TW': 'zh-TW', 'ga': 'ga-IE'}


def voice_for(lang):
    """언어별 읽기 목소리. 정해 둔 목소리가 없으면 그 언어 지역의 첫 목소리."""
    if lang in M.VOICES:
        return M.VOICES[lang]
    loc = LOCALES.get(lang)
    if not loc:
        return None
    if not M._VOICE_LIST:
        try:
            M.voices_for('ko')
        except Exception:
            return None
    v = next((n for n in M._VOICE_LIST if n.startswith(loc + '-')), None)
    if v:
        M.VOICES[lang] = v
    return v


P.voice_for = lambda lang: voice_for(lang)


@route('GET', r'/api/langs')
def langs(c):
    return {'langs': P.LANGS, 'voices': sorted(set(M.VOICES) | set(LOCALES))}


# ---------- 개정 이력: 덮어쓰기 전 내용을 남기고 되돌린다 ----------
def snapshot(kind, vid, uid):
    if kind == 'steps':
        rows = q('select ord,start,end,title,note,warn,image from steps where version_id=? order by ord', (vid,))
    elif kind.startswith('subs:'):
        rows = q('select ord,start,end,text,confirmed from subs where version_id=? and lang=? order by ord', (vid, kind[5:]))
    else:
        rows = q('select start,end,kind,x,y,w,h,color,text from annotations where version_id=? order by start', (vid,))
    if rows:
        x('insert into revisions(version_id,kind,data,user_id) values(?,?,?,?)', (vid, kind, json.dumps(rows, ensure_ascii=False), uid))


P.BEFORE_SAVE.append(snapshot)


@route('GET', r'/api/versions/(\d+)/revisions', 'manager')
def revisions(c, vid):
    rows = q('select r.id,r.kind,r.created,u.name,length(r.data) size from revisions r left join users u on u.id=r.user_id where version_id=? order by r.id desc limit 100', (vid,))
    return {'rows': rows}


@route('POST', r'/api/revisions/(\d+)/restore', 'manager')
def restore(c, rid):
    r = need(one('select * from revisions where id=?', (rid,)))
    vid, kind, rows = r['version_id'], r['kind'], json.loads(r['data'])
    snapshot(kind, vid, c.u['id'])

    def w(db):
        if kind == 'steps':
            db.execute('delete from steps where version_id=?', (vid,))
            db.executemany('insert into steps(version_id,ord,start,end,title,note,warn,image) values(?,?,?,?,?,?,?,?)',
                           [(vid, d['ord'], d['start'], d['end'], d['title'], d['note'], d['warn'], d['image']) for d in rows])
        elif kind.startswith('subs:'):
            db.execute('delete from subs where version_id=? and lang=?', (vid, kind[5:]))
            db.executemany('insert into subs(version_id,lang,ord,start,end,text,confirmed) values(?,?,?,?,?,?,?)',
                           [(vid, kind[5:], d['ord'], d['start'], d['end'], d['text'], d['confirmed']) for d in rows])
        else:
            db.execute('delete from annotations where version_id=?', (vid,))
            db.executemany('insert into annotations(version_id,start,end,kind,x,y,w,h,color,text) values(?,?,?,?,?,?,?,?,?,?)',
                           [(vid, d['start'], d['end'], d['kind'], d['x'], d['y'], d['w'], d['h'], d['color'], d['text']) for d in rows])
    many(w); c.log('revision_restore', f'{vid}:{kind}')
    return {'ok': True}


# ---------- 문서·단계 글 번역 ----------
def steps_trans_job(vid, lang):
    key = 'steps-' + lang
    try:
        v = version(vid); m = one('select id,title from manuals where id=?', (v['manual_id'],))
        src = q('select * from steps where version_id=? order by ord', (vid,))
        items = [{'i': r['ord'], 'title': r['title'], 'note': r['note'] or '', 'warn': r['warn'] or ''} for r in src] + [{'i': -1, 'title': m['title'], 'note': '', 'warn': ''}]
        out = {}
        for k in range(0, len(items), 8):  # 8개씩 묶어 JSON 으로 번역(필드마다 부르면 느리다)
            chunk = items[k:k + 8]
            r = ollama(f'Translate the Korean values of "title", "note", "warn" in this JSON array of workplace-safety manual steps into {P.LANGS[lang]}. '
                       'Keep "i" unchanged and keep empty strings empty. Output only the JSON array.\n\n' + json.dumps(chunk, ensure_ascii=False))
            mm = re.search(r'\[.*\]', r, re.S)
            try:
                got = {int(d['i']): d for d in json.loads(mm.group(0)) if isinstance(d, dict)} if mm else {}
            except (ValueError, KeyError, TypeError):
                got = {}
            for it in chunk:  # 묶음 번역에서 빠진 것만 하나씩
                d = got.get(it['i']) or {f: (ollama(f'Translate into {P.LANGS[lang]}. Output only the translation.\n\n{it[f]}').strip() if it[f].strip() else '') for f in ('title', 'note', 'warn')}
                out[it['i']] = d
        rows = [(vid, r['ord'], lang, str(out[r['ord']].get('title') or '')[:200], str(out[r['ord']].get('note') or '')[:4000], str(out[r['ord']].get('warn') or '')[:500]) for r in src]
        title = str(out[-1].get('title') or m['title'])[:200]

        def w(db):
            db.execute('delete from step_i18n where version_id=? and lang=?', (vid, lang))
            db.executemany('insert into step_i18n values(?,?,?,?,?,?)', rows)
            db.execute('insert or replace into manual_i18n values(?,?,?)', (m['id'], lang, title))
        many(w); job(vid, key, 'done')
    except Exception as ex:
        job(vid, key, 'failed', ex)


@route('POST', r'/api/versions/(\d+)/steps/translate', 'manager')
def steps_trans(c, vid):
    lang = c.d.get('lang')
    if lang not in P.LANGS or lang == 'ko':
        raise E(400, '언어가 올바르지 않습니다.')
    if not one('select 1 x from steps where version_id=?', (vid,)):
        raise E(400, '번역할 단계가 없습니다.')
    job(vid, 'steps-' + lang, 'running')
    threading.Thread(target=steps_trans_job, args=(int(vid), lang), daemon=True).start()
    c.log('steps_translate', f'{vid}:{lang}')
    return {'ok': True}


@route('GET', r'/api/versions/(\d+)/steps')
def steps_get(c, vid):
    version_for(c, vid)
    lang = c.arg('lang', 'ko')
    rows = q('select * from steps where version_id=? order by ord', (vid,))
    tr = {r['ord']: r for r in q('select * from step_i18n where version_id=? and lang=?', (vid, lang))}
    for r in rows:
        t = tr.get(r['ord'])
        if t:
            r.update(title=t['title'] or r['title'], note=t['note'] or r['note'], warn=t['warn'] or r['warn'])
    return {'steps': rows, 'langs': [r['lang'] for r in q('select distinct lang from step_i18n where version_id=?', (vid,))]}


@route('PUT', r'/api/versions/(\d+)/steps/i18n', 'manager')
def steps_i18n_put(c, vid):
    lang = c.d.get('lang'); rows = c.d.get('steps')
    if lang not in P.LANGS or not isinstance(rows, list):
        raise E(400, '값이 올바르지 않습니다.')
    many(lambda db: [db.execute('insert or replace into step_i18n values(?,?,?,?,?,?)', (vid, int(r.get('ord', i)), lang, s(r, 'title', 200), s(r, 'note', 4000), s(r, 'warn', 500))) for i, r in enumerate(rows)])
    return {'ok': True}


# ---------- 폴더(공정 → 현상 → 원인·대책) ----------
@route('GET', r'/api/folders')
def folders(c):
    return {'rows': q('select * from folders order by parent_id, ord, name')}


@route('POST', r'/api/folders', 'manager')
def folder_new(c):
    pid = c.d.get('parent_id') or None
    if pid and not one('select 1 x from folders where id=?', (pid,)):
        raise E(400, '상위 폴더가 없습니다.')
    return {'id': x('insert into folders(parent_id,name) values(?,?)', (pid, s(c.d, 'name', 100, True)))}


@route('PUT', r'/api/folders/(\d+)', 'manager')
def folder_put(c, fid):
    f = need(one('select * from folders where id=?', (fid,)))
    pid = c.d.get('parent_id', f['parent_id']) or None
    p = pid
    while p:  # 자기 아래로 옮기면 고리가 생긴다
        if int(p) == int(fid):
            raise E(400, '하위 폴더 아래로는 옮길 수 없습니다.')
        p = (one('select parent_id from folders where id=?', (p,)) or {}).get('parent_id')
    x('update folders set name=?,parent_id=? where id=?', (s(c.d, 'name', 100) or f['name'], pid, fid))
    return {'ok': True}


@route('DELETE', r'/api/folders/(\d+)', 'manager')
def folder_del(c, fid):
    f = need(one('select * from folders where id=?', (fid,)))
    many(lambda db: [db.execute('update folders set parent_id=? where parent_id=?', (f['parent_id'], fid)),
                     db.execute('update manuals set folder_id=? where folder_id=?', (f['parent_id'], fid)), db.execute('delete from folders where id=?', (fid,))])
    return {'ok': True}


@route('PUT', r'/api/manuals/(\d+)/folder', 'manager')
def manual_folder(c, mid):
    fid = c.d.get('folder_id') or None
    if fid and not one('select 1 x from folders where id=?', (fid,)):
        raise E(400, '폴더가 없습니다.')
    x('update manuals set folder_id=? where id=?', (fid, mid))
    return {'ok': True}


# ---------- 교육 과정 편집·진행 리포트 ----------
@route('PUT', r'/api/courses/(\d+)', 'manager')
def course_put(c, cid):
    k = need(one('select * from courses where id=?', (cid,)))
    ids = [int(i) for i in c.d.get('manual_ids') or []]
    if not ids or len(set(ids)) != len(ids):
        raise E(400, '매뉴얼을 하나 이상, 겹치지 않게 고르세요.')

    def w(db):
        db.execute('update courses set title=? where id=?', (s(c.d, 'title', 200) or k['title'], cid))
        db.execute('delete from course_items where course_id=?', (cid,))
        db.executemany('insert into course_items values(?,?,?)', [(cid, m, i) for i, m in enumerate(ids)])
    many(w); c.log('course_update', cid)
    return {'ok': True}


@route('DELETE', r'/api/courses/(\d+)', 'manager')
def course_del(c, cid):
    many(lambda db: [db.execute('delete from course_items where course_id=?', (cid,)), db.execute('delete from courses where id=?', (cid,))])
    return {'ok': True}


def course_report_data(cid):
    k = need(one('select * from courses where id=?', (cid,)))
    items = q('select m.* from course_items i join manuals m on m.id=i.manual_id where i.course_id=? order by i.ord', (cid,))
    ids = [m['id'] for m in items]
    users = q(f"select distinct u.id,u.name,u.dept,u.site from assigns a join users u on u.id=a.user_id where u.active=1 and a.manual_id in ({','.join('?' * len(ids)) or 'null'}) order by u.dept,u.name", tuple(ids))
    rows = []
    for u in users:
        st = [P.status_of(u['id'], m) for m in items]
        rows.append({**u, 'cells': st, 'done': st.count('done'), 'pct': round(100 * st.count('done') / max(1, len(items)))})
    return k, items, rows


@route('GET', r'/api/courses/(\d+)/report', 'manager')
def course_report(c, cid):
    k, items, rows = course_report_data(cid)
    return {'course': k, 'items': [{'id': m['id'], 'title': m['title']} for m in items], 'rows': rows,
            'avg': round(sum(r['pct'] for r in rows) / len(rows)) if rows else 0}


@route('GET', r'/api/courses/(\d+)/report\.xlsx', 'manager')
def course_report_x(c, cid):
    k, items, rows = course_report_data(cid)
    L = {'done': '이수', 'outdated': '재이수 필요', 'doing': '진행 중', 'todo': '미시작'}
    return P.xlsx(c, f'course-{cid}', ['이름', '부서', '사업장', *[m['title'] for m in items], '진행률(%)'],
                  [[r['name'], r['dept'], r['site'], *[L[x_] for x_ in r['cells']], r['pct']] for r in rows])


# ---------- 스킬 수정·삭제 ----------
@route('PUT', r'/api/skills/(\d+)', 'manager')
def skill_put(c, sid):
    k = need(one('select * from skills where id=?', (sid,)))
    ids = [int(i) for i in c.d.get('manual_ids', json.loads(k['manual_ids']))]
    x('update skills set name=?,category=?,manual_ids=? where id=?', (s(c.d, 'name', 120) or k['name'], str(c.d.get('category', k['category']))[:80], json.dumps(ids), sid))
    return {'ok': True}


@route('DELETE', r'/api/skills/(\d+)', 'manager')
def skill_del(c, sid):
    need(one('select 1 x from skills where id=?', (sid,)))
    many(lambda db: [db.execute(f'delete from {t} where skill_id=?', (sid,)) for t in ('evals', 'skill_plans')] + [db.execute('delete from skills where id=?', (sid,))])
    return {'ok': True}


# ---------- PDF 작업표준서 → 매뉴얼 초안 / 교육 과정 ----------
HEAD = re.compile(r'^\s*(?:\d{1,2}[.)]|[0-9]{1,2}\s*장|제\s*\d+\s*[장절]|[가-하][.)]|[■□●◆▶※])\s*\S')


def split_sections(text, most=8):
    """제목처럼 보이는 줄(1. / 제1장 / 가. / ■ …)에서 나눈다. 너무 잘거나 하나뿐이면 글자 수로 나눈다."""
    lines = [l for l in text.splitlines() if l.strip()]
    parts, cur = [], []
    for l in lines:
        if HEAD.match(l) and sum(len(x) for x in cur) > 300:
            parts.append('\n'.join(cur)); cur = []
        cur.append(l)
    if cur:
        parts.append('\n'.join(cur))
    if len(parts) < 2:
        parts = [text[i:i + 2500] for i in range(0, len(text), 2500)]
    while len(parts) > most:  # 가장 짧은 이웃끼리 합친다
        i = min(range(len(parts) - 1), key=lambda k: len(parts[k]) + len(parts[k + 1]))
        parts[i:i + 2] = [parts[i] + '\n' + parts[i + 1]]
    return [p[:5000] for p in parts]


def ai_section(part):
    r = ollama('다음은 작업표준서의 한 부분이다. 현장 교육용 매뉴얼 하나로 만들어라. JSON 객체 하나만 출력하라: {"title": 매뉴얼 제목, "steps": [{"title": 단계 제목, "note": 할 일 설명, "warn": 안전 주의(없으면 빈 문자열)}]}. 원문에 없는 내용은 만들지 마라.\n\n' + part)
    m = re.search(r'\{.*\}', r, re.S)
    try:
        d = json.loads(m.group(0)) if m else {}
    except ValueError:
        d = {}
    st = [{'title': str(t.get('title', ''))[:200], 'note': str(t.get('note', ''))[:2000], 'warn': str(t.get('warn', ''))[:500]} for t in d.get('steps') or [] if isinstance(t, dict) and str(t.get('title', '')).strip()]
    return {'title': str(d.get('title') or part.strip().splitlines()[0])[:200], 'steps': st[:40]} if st else None


AI_JOBS = {}  # ponytail: 서버 메모리. 다시 시작하면 진행 중 작업은 사라진다(다시 올리면 됨)


def course_job(token, text, name, uid):
    try:
        parts = split_sections(text); secs = []
        for k, part in enumerate(parts):
            AI_JOBS[token] = {'state': 'running', 'done': k, 'total': len(parts)}
            d = ai_section(part)
            if d:
                secs.append(d)
        if not secs:
            raise RuntimeError('AI가 과정을 나누지 못했습니다. 다시 시도하세요.')

        def w(db):
            ids = [new_doc_manual(db, d['title'], d['steps'], uid, name) for d in secs]
            cid = db.execute('insert into courses(title) values(?)', (name,)).lastrowid
            db.executemany('insert into course_items values(?,?,?)', [(cid, m_, i) for i, m_ in enumerate(ids)])
            return cid, ids
        cid, ids = many(w)
        AI_JOBS[token] = {'state': 'done', 'course_id': cid, 'manual_ids': ids}
    except Exception as ex:
        AI_JOBS[token] = {'state': 'failed', 'error': str(ex)[:300] if isinstance(ex, RuntimeError) else 'AI 실행 환경(Ollama)에 연결하지 못했습니다.'}


def new_doc_manual(db, title, steps, uid, category=''):
    mid = db.execute("insert into manuals(title,category,owner_id,kind) values(?,?,?,'doc')", (title, category, uid)).lastrowid
    vid = db.execute("insert into versions(manual_id,no,reason,author_id,state) values(?,1,'작업표준서에서 자동 작성',?,'ready')", (mid, uid)).lastrowid
    db.execute('update manuals set current_version=? where id=?', (vid, mid))
    db.executemany("insert into steps(version_id,ord,start,end,title,note,warn,image) values(?,?,0,0,?,?,?,'')", [(vid, i, t['title'], t['note'], t['warn']) for i, t in enumerate(steps)])
    return mid


def read_doc(c):
    text = M.extract_text(M.raw_body(c, 20 * 1024 * 1024)).strip()
    if len(text) < 20:
        raise E(400, '문서에서 글을 읽지 못했습니다. 글자가 있는 PDF·Word·텍스트 파일을 올리세요.')
    return text


@route('POST', r'/api/ai/manual', 'manager', raw=True)
def ai_manual(c):
    from urllib.parse import unquote
    text = read_doc(c); name = unquote(c.h.headers.get('X-Name', ''))[:200].strip() or '작업표준서'
    try:
        r = ollama('다음 작업 절차서를 현장 교육용 매뉴얼 단계로 나눠라. JSON 배열만 출력하라. 각 항목은 {"title": 짧은 단계 제목, "note": 해야 할 일 설명, "warn": 안전 주의사항(없으면 빈 문자열)}. 원문에 없는 내용은 만들지 마라.\n\n' + text[:6000])
    except Exception:
        raise E(503, 'AI 실행 환경(Ollama)에 연결하지 못했습니다.')
    steps = [{'title': str(d['title'])[:200], 'note': str(d.get('note', ''))[:2000], 'warn': str(d.get('warn', ''))[:500]} for d in M.json_list(r)]
    if not steps:
        raise E(502, 'AI가 단계를 만들지 못했습니다. 다시 시도하세요.')
    mid = many(lambda db: new_doc_manual(db, name, steps, c.u['id']))
    c.log('ai_manual', mid)
    return {'id': mid, 'steps': len(steps)}


@route('POST', r'/api/ai/course', 'manager', raw=True)
def ai_course(c):
    import secrets
    from urllib.parse import unquote
    text = read_doc(c); name = unquote(c.h.headers.get('X-Name', ''))[:200].strip() or '작업표준서 과정'
    token = secrets.token_hex(8); AI_JOBS[token] = {'state': 'running', 'done': 0, 'total': 1}
    threading.Thread(target=course_job, args=(token, text, name, c.u['id']), daemon=True).start()
    c.log('ai_course', name)
    return {'token': token}


@route('GET', r'/api/ai/course/([0-9a-f]{16})', 'manager')
def ai_course_state(c, token):
    return need(AI_JOBS.get(token), '작업을 찾을 수 없습니다.')


# ---------- 업로드 → 받아쓰기 → 단계 자동 ----------
def auto_pipeline(vid, uid):
    import time
    for _ in range(4 * 3600):
        v = one('select state from versions where id=?', (vid,))
        if not v or v['state'] != 'processing':
            break
        time.sleep(1)
    if not v or v['state'] != 'ready' or not os.path.exists(P.ASR_PY):
        return
    job(vid, 'ko', 'running'); P.asr_job(vid)
    if (one("select state from subjobs where version_id=? and lang='ko'", (vid,)) or {}).get('state') != 'done':
        return
    job(vid, 'auto', 'running')
    try:
        steps = M.make_autosteps(vid)
        snapshot('steps', vid, uid)
        many(lambda db: [db.execute('delete from steps where version_id=?', (vid,)),
                         db.executemany("insert into steps(version_id,ord,start,end,title,note,warn,image) values(?,?,?,?,?,?,?,'')",
                                        [(vid, i, t['start'], t['end'], t['title'], t['note'], t['warn']) for i, t in enumerate(steps)])])
        job(vid, 'auto', 'done')
    except Exception as ex:
        job(vid, 'auto', 'failed', ex)


P.AFTER_UPLOAD.append(lambda vid, uid, auto: auto and threading.Thread(target=auto_pipeline, args=(vid, uid), daemon=True).start())


# ---------- 자막·도형·단계 제목을 입힌 영상 내보내기 ----------
FONT = next((f for f in ('C:/Windows/Fonts/malgun.ttf', '/usr/share/fonts/truetype/nanum/NanumGothic.ttf', '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc') if os.path.exists(f)), '')


def ff_path(p):
    return p.replace('\\', '/').replace(':', '\\:')


def export_job(vid, lang):
    key = 'export-' + lang
    tmp = os.path.join(VIDEOS, uuid.uuid4().hex); os.makedirs(tmp)
    try:
        if not FONT:
            raise RuntimeError('글꼴이 없어 글자를 입힐 수 없습니다(서버에 fonts-nanum 필요).')
        v = version(vid); fs = []
        def text(i, t, a, b, xexpr, yexpr, size, box):
            f = os.path.join(tmp, f'{i}.txt'); open(f, 'w', encoding='utf-8').write(t)
            fs.append(f"drawtext=fontfile='{ff_path(FONT)}':textfile='{ff_path(f)}':x={xexpr}:y={yexpr}:fontsize={size}:fontcolor=white:box=1:boxcolor={box}:boxborderw=8:enable='between(t,{a:.2f},{b:.2f})'")
        n = 0
        for r in q('select start,end,title from steps where version_id=? order by ord', (vid,)):
            text(f's{n}', r['title'], r['start'], r['end'], '20', '20', 'h/22', '0x062540@0.85'); n += 1
        for r in q('select * from annotations where version_id=?', (vid,)):
            col = r['color'].replace('#', '0x')
            if r['kind'] == 'text':
                text(f'a{n}', r['text'] or '', r['start'], r['end'], f'w*{r["x"]:.3f}', f'h*{r["y"]:.3f}', 'h/18', col + '@0.8')
            else:
                fs.append(f"drawbox=x=iw*{min(r['x'], r['x'] + r['w']):.3f}:y=ih*{min(r['y'], r['y'] + r['h']):.3f}:w=iw*{abs(r['w']):.3f}:h=ih*{abs(r['h']):.3f}:color={col}:t=6:enable='between(t,{r['start']:.2f},{r['end']:.2f})'")
            n += 1
        subs = q('select start,end,text from subs where version_id=? and lang=? and confirmed=1 order by ord', (vid, lang))
        if len(subs) > 400:
            raise RuntimeError('자막이 400줄을 넘어 한 번에 입힐 수 없습니다.')
        for i, r in enumerate(subs):
            text(f'u{i}', r['text'], r['start'], r['end'], '(w-text_w)/2', 'h-text_h-30', 'h/20', 'black@0.6')
        out = os.path.join(VIDEOS, f'{uuid.uuid4().hex}.mp4')
        script = os.path.join(tmp, 'f.txt'); open(script, 'w', encoding='utf-8').write(','.join(fs) or 'null')
        p = subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', os.path.join(VIDEOS, v['file']), '-/vf', script, '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '23',
                            '-c:a', 'copy', '-movflags', '+faststart', out], capture_output=True, text=True, encoding='utf8', errors='replace', timeout=4 * 3600)
        if p.returncode and '-/vf' in p.stderr:  # 옛 ffmpeg(7 이하)
            p = subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', os.path.join(VIDEOS, v['file']), '-filter_script:v', script, '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '23',
                                '-c:a', 'copy', '-movflags', '+faststart', out], capture_output=True, text=True, encoding='utf8', errors='replace', timeout=4 * 3600)
        if p.returncode:
            raise RuntimeError(p.stderr[-300:])
        old = one('select file from exports where version_id=? and lang=?', (vid, lang))
        x('insert or replace into exports values(?,?,?)', (vid, lang, os.path.basename(out)))
        if old and os.path.exists(os.path.join(VIDEOS, old['file'])):
            os.remove(os.path.join(VIDEOS, old['file']))
        job(vid, key, 'done')
    except Exception as ex:
        job(vid, key, 'failed', ex)
    finally:
        import shutil; shutil.rmtree(tmp, ignore_errors=True)


@route('POST', r'/api/versions/(\d+)/export', 'manager')
def export(c, vid):
    v = version(vid); lang = c.d.get('lang') or 'ko'
    if not v['file'] or lang not in P.LANGS:
        raise E(400, '영상 매뉴얼에서 언어를 골라 주세요.')
    job(vid, 'export-' + lang, 'running')
    threading.Thread(target=export_job, args=(int(vid), lang), daemon=True).start()
    return {'ok': True}


@route('GET', r'/api/versions/(\d+)/export\.mp4', 'manager')
def export_get(c, vid):
    r = need(one('select e.file,m.title from exports e join versions v on v.id=e.version_id join manuals m on m.id=v.manual_id where e.version_id=? and e.lang=?', (vid, c.arg('lang', 'ko'))), '내보낸 영상이 없습니다.')
    from urllib.parse import quote
    c.h.send(200, open(os.path.join(VIDEOS, r['file']), 'rb').read(), 'video/mp4', extra=[('Content-Disposition', f"attachment; filename*=UTF-8''{quote(r['title'])}-{c.arg('lang', 'ko')}.mp4")])
    return Done


# ---------- 사용자별 세부 권한 ----------
PERMS = {'manual_edit': '매뉴얼 만들기·편집', 'approve': '승인', 'assign': '교육 배정', 'reports': '현황·리포트 보기',
         'forms': '점검표 관리', 'safety': '중대재해 의무 관리', 'skills': '스킬 평가', 'onboarding': '도입 관리'}
PERM_RULES = [  # (권한, 방법, 경로 정규식). 관리자 이상에게만 적용(근로자는 원래 못 하는 일)
    ('manual_edit', 'POST|PUT|DELETE', r'/api/(manuals(/\d+)?(/(versions|docversion|quiz|folder|standard))?|versions/\d+/.*|images|ai/(outline|manual|course)|glossary.*|folders.*|revisions/\d+/restore)$'),
    ('approve', 'POST', r'/api/approvals/\d+$'),
    ('assign', 'POST', r'/api/(manuals|courses)/\d+/assign$'),
    ('reports', 'GET', r'/api/(matrix|unfinished|completions|usage|dashboard|report|courses/\d+/report|manuals/\d+/report).*'),
    ('forms', 'POST|PUT|DELETE', r'/api/(forms.*|submissions/\d+/review|ai/checklist)$'),
    ('safety', 'PUT|GET', r'/api/safety.*'),
    ('skills', 'POST|PUT|DELETE', r'/api/skills(/\d+|/eval|/plan)?$'),
    ('onboarding', 'POST|PUT|DELETE', r'/api/onboarding/.*'),
]
PERM_RX = [(k, set(m.split('|')), re.compile('^' + p)) for k, m, p in PERM_RULES]


def perm_ok(u, method, path):
    denied = set(filter(None, (u.get('perms') or '').split(',')))
    if not denied or u['role'] == 'admin':
        return True
    return not any(k in denied and method in ms and rx.match(path) for k, ms, rx in PERM_RX)


@route('GET', r'/api/perms', 'admin')
def perms(c):
    return {'perms': PERMS, 'users': {u['id']: [p for p in (u['perms'] or '').split(',') if p] for u in q('select id,perms from users')}}


@route('PUT', r'/api/users/(\d+)/perms', 'admin')
def perms_put(c, uid):
    need(one('select 1 x from users where id=?', (uid,)))
    denied = [p for p in c.d.get('denied') or [] if p in PERMS]
    x('update users set perms=? where id=?', (','.join(denied), uid)); c.log('perms', f'{uid}:{",".join(denied)}')
    return {'ok': True}


# ---------- 도입 지원: 목표 · 3개월 계획 · 정기 점검 회의 ----------
@route('GET', r'/api/onboarding', 'manager')
def onboarding(c):
    goals = q('select g.*,u.name owner from ob_goals g left join users u on u.id=g.owner_id order by g.id')
    plan = q('select p.*,u.name owner from ob_plan p left join users u on u.id=p.owner_id order by p.week, case p.priority when "상" then 0 when "중" then 1 else 2 end, p.id')
    meets = q('select * from ob_meetings order by day desc, id desc')
    # 지표 실측: 앱 데이터에서 바로 센다
    live = {'공개 매뉴얼': one("select count(*) n from manuals where status='published'")['n'], '이수 건수': one('select count(*) n from completions')['n'],
            '활성 사용자': one('select count(*) n from users where active=1')['n'], '점검표 제출': one('select count(*) n from submissions')['n'],
            '30일 로그인 사용자': one("select count(distinct user_id) n from audit where action like 'login%' and action not like '%fail' and created>=date('now','-30 day')")['n']}
    return {'goals': goals, 'plan': plan, 'meetings': meets, 'live': live, 'done_pct': round(100 * sum(1 for p in plan if p['status'] == 'done') / len(plan)) if plan else 0}


@route('POST', r'/api/onboarding/goals', 'manager')
def ob_goal(c):
    return {'id': x('insert into ob_goals(title,metric,target,due,owner_id) values(?,?,?,?,?)', (s(c.d, 'title', 200, True), s(c.d, 'metric', 100), s(c.d, 'target', 100), s(c.d, 'due', 10), c.d.get('owner_id') or c.u['id']))}


@route('PUT', r'/api/onboarding/goals/(\d+)', 'manager')
def ob_goal_put(c, gid):
    g = need(one('select * from ob_goals where id=?', (gid,)))
    x('update ob_goals set current=?,target=?,due=? where id=?', (str(c.d.get('current', g['current']))[:100], str(c.d.get('target', g['target']))[:100], str(c.d.get('due', g['due']))[:10], gid))
    return {'ok': True}


@route('POST', r'/api/onboarding/plan', 'manager')
def ob_plan(c):
    wk = int(fnum(c.d.get('week', 1), '주차'))
    if not 1 <= wk <= 13:
        raise E(400, '주차는 1~13(약 3개월) 사이입니다.')
    pr = c.d.get('priority') if c.d.get('priority') in ('상', '중', '하') else '중'
    return {'id': x('insert into ob_plan(week,title,priority,owner_id,note) values(?,?,?,?,?)', (wk, s(c.d, 'title', 200, True), pr, c.d.get('owner_id') or c.u['id'], s(c.d, 'note', 1000)))}


@route('PUT', r'/api/onboarding/plan/(\d+)', 'manager')
def ob_plan_put(c, pid):
    p = need(one('select * from ob_plan where id=?', (pid,)))
    st = c.d.get('status', p['status'])
    if st not in ('todo', 'doing', 'done'):
        raise E(400, '상태 값이 올바르지 않습니다.')
    x('update ob_plan set status=?,note=? where id=?', (st, str(c.d.get('note', p['note']))[:1000], pid))
    return {'ok': True}


@route('POST', r'/api/onboarding/meetings', 'manager')
def ob_meet(c):
    kind = c.d.get('kind') if c.d.get('kind') in ('정기 점검', '온라인 회의', '현장 방문', '착수 회의') else '정기 점검'
    mid = x('insert into ob_meetings(day,kind,attendees,notes,actions,created_by) values(?,?,?,?,?,?)',
            (s(c.d, 'day', 10, True), kind, s(c.d, 'attendees', 300), s(c.d, 'notes', 4000, True), s(c.d, 'actions', 2000), c.u['id']))
    for a in [l.strip('-• ').strip() for l in s(c.d, 'actions', 2000).splitlines() if l.strip()]:  # 개선 제안은 개선 과제로 넘긴다
        x('insert into tasks(title,assignee_id,status) values(?,?,?)', (('[회의] ' + a)[:300], c.u['id'], 'open'))
    return {'id': mid}


# ---------- 보고서(PDF): 교육·현장 기록·점검표·중대재해 의무 ----------
def _font():
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    if 'K' not in pdfmetrics.getRegisteredFontNames():
        if not FONT:
            raise E(503, '서버에 한글 글꼴이 없어 보고서를 만들 수 없습니다.')
        pdfmetrics.registerFont(TTFont('K', FONT, subfontIndex=0) if FONT.endswith('.ttc') else TTFont('K', FONT))


SECTIONS = {'edu': '교육 이수', 'forms': '현장 점검표', 'records': '위험요인·의견 등 현장 기록', 'safety': '중대재해 의무 점검', 'tasks': '개선 과제', 'manuals': '매뉴얼 현황'}


def report_data(frm, to, secs):
    w = lambda col: f" and date({col}) between ? and ?"
    a = (frm, to)
    out = []
    if 'edu' in secs:
        rows = q('select c.created,u.name,u.dept,m.title,c.score,c.lang from completions c join users u on u.id=c.user_id join manuals m on m.id=c.manual_id where 1=1' + w('c.created') + ' order by c.created', a)
        un = P.unfinished_rows()
        out.append(('edu', f'기간 이수 {len(rows)}건 · 현재 미이수·기한 경과 {len(un)}명분', ['이수 시각', '이름', '부서', '교육', '점수', '언어'], [[r['created'], r['name'], r['dept'], r['title'], r['score'], P.LANGS.get(r['lang'], r['lang'])] for r in rows]))
    if 'forms' in secs:
        rows = q('select s.created,f.title,u.name,s.abnormal,s.status from submissions s join forms f on f.id=s.form_id left join users u on u.id=s.user_id where 1=1' + w('s.created') + ' order by s.created', a)
        ab = sum(1 for r in rows if r['abnormal'])
        out.append(('forms', f'제출 {len(rows)}건 · 이상 {ab}건', ['시각', '점검표', '점검자', '판정', '승인'], [[r['created'], r['title'], r['name'] or '', '이상' if r['abnormal'] else '정상', {'ok': '승인', 'reject': '반려'}.get(r['status'], '대기')] for r in rows]))
    if 'records' in secs:
        rows = q('select r.created,r.kind,u.name,r.data,r.status from records r left join users u on u.id=r.user_id where 1=1' + w('r.created') + ' order by r.created', a)
        K = {'hazard': '위험요인', 'opinion': '의견', 'budget': '예산', 'evaluation': '평가', 'drill': '비상 대응', 'contractor': '도급', 'legal': '관계 법령'}
        out.append(('records', f'기록 {len(rows)}건 · 조치 완료 {sum(1 for r in rows if r["status"] == "done")}건', ['시각', '구분', '작성', '제목', '조치', '상태'],
                    [[r['created'], K.get(r['kind'], r['kind']), (r['name'] or '') if not json.loads(r['data']).get('anon') else '익명', json.loads(r['data']).get('title', ''), json.loads(r['data']).get('action', ''), {'open': '접수', 'doing': '조치 중', 'done': '완료'}.get(r['status'], r['status'])] for r in rows]))
    if 'safety' in secs:
        h = P.cur_half(); rows = P.safety_rows(h)
        out.append(('safety', f'{h} 점검 {sum(1 for r in rows if r.get("status") == "done")}/{len(rows)}', ['조문', '항목', '상태', '증빙', '메모'],
                    [[r['article'], r['title'], {'done': '완료', 'doing': '진행', 'todo': '미점검'}.get(r.get('status'), r.get('status') or '미점검'), r.get('evidence', ''), r.get('memo', '')] for r in rows]))
    if 'tasks' in secs:
        rows = q('select t.created,t.title,u.name,t.status,t.due from tasks t left join users u on u.id=t.assignee_id where 1=1' + w('t.created') + ' order by t.created', a)
        out.append(('tasks', f'과제 {len(rows)}건', ['등록', '과제', '담당', '상태', '기한'], [[r['created'], r['title'], r['name'] or '', r['status'], r['due'] or ''] for r in rows]))
    if 'manuals' in secs:
        rows = q("select m.title,m.kind,m.status,v.no,(select count(*) from completions c where c.manual_id=m.id) n from manuals m left join versions v on v.id=m.current_version where m.status!='archived' order by m.id")
        out.append(('manuals', f'매뉴얼 {len(rows)}개', ['제목', '종류', '상태', '버전', '이수'], [[r['title'], '문서' if r['kind'] == 'doc' else '영상', {'published': '공개', 'draft': '초안', 'review': '검토'}.get(r['status'], r['status']), f"v{r['no'] or 0}", r['n']] for r in rows]))
    return out


@route('GET', r'/api/report\.pdf', 'manager')
def report_pdf(c):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    frm, to = c.arg('from') or date.today().replace(day=1).isoformat(), c.arg('to') or date.today().isoformat()
    if not (re.fullmatch(r'\d{4}-\d\d-\d\d', frm) and re.fullmatch(r'\d{4}-\d\d-\d\d', to)):
        raise E(400, '기간 형식이 올바르지 않습니다.')
    secs = [k for k in c.arg('sections', ','.join(SECTIONS)).split(',') if k in SECTIONS] or list(SECTIONS)
    _font()
    st = lambda n, sz, **k: ParagraphStyle(n, fontName='K', fontSize=sz, leading=sz * 1.4, **k)
    T, H, B, S = st('t', 18), st('h', 13, spaceBefore=10), st('b', 9), st('s', 8)
    title = s({'t': c.arg('title')}, 't', 100) or '안전·교육 보고서'
    els = [Paragraph(title, T), Paragraph(f'기간 {frm} ~ {to} · 작성 {c.u["name"]} · 출력 {date.today().isoformat()}', B), Spacer(1, 8)]
    for k, summary, head, rows in report_data(frm, to, secs):
        els += [Paragraph(SECTIONS[k], H), Paragraph(summary, B), Spacer(1, 4)]
        if rows:
            data = [[Paragraph(str(h_), S) for h_ in head]] + [[Paragraph(str(v)[:300], S) for v in r] for r in rows[:500]]
            t = Table(data, repeatRows=1)
            t.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#062540')), ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                                   ('GRID', (0, 0), (-1, -1), .3, colors.HexColor('#c8ced8')), ('VALIGN', (0, 0), (-1, -1), 'TOP')]))
            for cell in data[0]:
                cell.style = ParagraphStyle('hw', parent=S, textColor=colors.white)
            els.append(t)
        else:
            els.append(Paragraph('기간 안의 기록이 없습니다.', S))
    b = io.BytesIO()
    SimpleDocTemplate(b, pagesize=landscape(A4), leftMargin=28, rightMargin=28, topMargin=28, bottomMargin=28, title=title).build(els)
    c.log('report_pdf', f'{frm}~{to}:{",".join(secs)}')
    c.h.send(200, b.getvalue(), 'application/pdf', extra=[('Content-Disposition', f'attachment; filename="report-{frm}-{to}.pdf"')])
    return Done


@route('GET', r'/api/report\.xlsx', 'manager')
def report_xlsx(c):
    from openpyxl import Workbook
    frm, to = c.arg('from') or date.today().replace(day=1).isoformat(), c.arg('to') or date.today().isoformat()
    secs = [k for k in c.arg('sections', ','.join(SECTIONS)).split(',') if k in SECTIONS] or list(SECTIONS)
    wb = Workbook(); wb.remove(wb.active)
    for k, summary, head, rows in report_data(frm, to, secs):
        ws = wb.create_sheet(SECTIONS[k][:30]); ws.append([summary]); ws.append(head)
        for r in rows:
            ws.append([("'" + v if isinstance(v, str) and v[:1] in '=+-@' else v) for v in r])
    b = io.BytesIO(); wb.save(b)
    c.h.send(200, b.getvalue(), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', extra=[('Content-Disposition', f'attachment; filename="report-{frm}-{to}.xlsx"')])
    return Done


@route('GET', r'/api/report/sections', 'manager')
def report_sections(c):
    return {'sections': SECTIONS}


# ---------- 운영 정책: 승인 필수 배포 ----------
@route('GET', r'/api/settings/policy', 'admin')
def policy(c):
    return {'approval_required': P.setting('approval_required') == '1'}


@route('PUT', r'/api/settings/policy', 'admin')
def policy_put(c):
    x('insert or replace into settings(k,v) values(?,?)', ('approval_required', '1' if c.d.get('approval_required') else '0'))
    c.log('policy', c.d.get('approval_required'))
    return {'ok': True}
