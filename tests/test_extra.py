"""원작 체크리스트 외부 채점(2026-11-09)으로 더한 기능 확인: 100개 언어·단계 번역, 개정 이력·되돌리기, 단계별 확인 테스트 기록,
폴더, 과정 편집·진행 리포트, PDF→매뉴얼·과정, 업로드 후 자막·단계 자동, 자막·도형을 입힌 영상 내보내기, 승인 필수 배포, 세부 권한,
그림 접근 제한, 읽기 음성 낡음 처리, 도입 관리, 보고서(PDF·엑셀).  실행: py tests/test_extra.py [--no-ai]"""
import http.cookiejar, io, json, os, subprocess, sys, tempfile, time, urllib.error, urllib.request

B = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AI = '--no-ai' not in sys.argv
tmp = tempfile.mkdtemp(); port = 8905; U = f'http://127.0.0.1:{port}'
srv = subprocess.Popen([sys.executable, os.path.join(B, 'server.py')], env=dict(os.environ, PORT=str(port), DATA_DIR=tmp, ADMIN_PASSWORD='Test-pass-1', PYTHONUTF8='1'), cwd=B, stdout=subprocess.DEVNULL)
n = 0
PNG = bytes.fromhex('89504e470d0a1a0a0000000d4948445200000001000000010806000000') + b'\x1f\x15\xc4\x89' + bytes.fromhex('0000000a49444154789c6300010000050001') + b'\r\n-\xb4' + bytes.fromhex('0000000049454e44ae426082')
PK = os.environ.get('SAMPLE_PDF', '')  # 시험용 작업표준서 PDF(없으면 AI 문서 시험 건너뜀)


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
            with s.op.open(urllib.request.Request(U + path, body, hd, method=method), timeout=600) as x:
                return x.status, x.read(), dict(x.headers)
        except urllib.error.HTTPError as e:
            return e.code, e.read(), dict(e.headers)

    def j(s, path, data=None, method=None, want=200, raw=None, headers=None):
        c, b, _ = s.r(path, data, method, raw, headers)
        ok(c == want, f'{method or ("POST" if data is not None or raw is not None else "GET")} {path} -> {c} {b[:200]}')
        return json.loads(b) if b[:1] in (b'{', b'[') else b


def wait(a, vid, key, secs=900):
    for _ in range(secs):
        j = [x for x in a.j(f'/api/versions/{vid}/status')['jobs'] if x['lang'] == key]
        if j and j[0]['state'] != 'running':
            return j[0]
        time.sleep(1)


def wait_ready(a, vid):
    for _ in range(300):
        if a.j(f'/api/versions/{vid}/status')['state'] == 'ready':
            return True
        time.sleep(1)


try:
    for _ in range(50):
        try:
            urllib.request.urlopen(U + '/', timeout=1); break
        except Exception:
            time.sleep(.2)
    a = S(); a.j('/api/login', dict(user='admin', password='Test-pass-1'))
    # 사용자: 관리자 1, 근로자 2(골조팀·설비팀)
    made = {c['login']: c['password'] for c in a.j('/api/users', {'users': [dict(login='mgr', name='박관리', role='manager', dept='공무팀'), dict(login='w1', name='김근로', dept='골조팀', lang='vi'), dict(login='w2', name='이근로', dept='설비팀')]})['created']}
    sess = {}
    for k, p in made.items():
        s_ = S(); s_.j('/api/login', dict(user=k, password=p)); s_.j('/api/me/password', {'old': p, 'new': p + 'Xy9!'}); s_.j('/api/login', dict(user=k, password=p + 'Xy9!')); sess[k] = s_
    m_, w1, w2 = sess['mgr'], sess['w1'], sess['w2']
    uid = {u['login']: u['id'] for u in a.j('/api/users')['users']}

    # 1 언어 100개 이상
    L = a.j('/api/langs')['langs']; ok(len(L) >= 100 and 'vi' in L and 'sw' in L, f'langs {len(L)}')

    # 2 영상 업로드 + 자동 자막·단계 (AI 있을 때)
    mid = a.j('/api/manuals', {'title': '비계 조립 안전', 'category': '안전'})['id']
    vid = a.j(f'/api/manuals/{mid}/versions', raw=open(os.path.join(B, 'tests', 'fixtures', 'sample.mp4'), 'rb').read(), headers={'X-Auto': '1'} if AI else {})['version_id']
    ok(wait_ready(a, vid), 'transcode')
    if AI:
        j = wait(a, vid, 'ko'); ok(j and j['state'] == 'done', f'auto asr {j}')
        j = wait(a, vid, 'auto', 300); ok(j and j['state'] == 'done', f'auto steps {j}')
        st = a.j(f'/api/manuals/{mid}')['steps']; ok(len(st) >= 1 and all(x['note'] for x in st), f'auto steps saved {st}')
    else:
        a.j(f'/api/versions/{vid}/subs', {'lang': 'ko', 'confirm': True, 'subs': [{'start': 0, 'end': 3, 'text': '안전모를 쓴다'}, {'start': 3, 'end': 7, 'text': '안전대를 건다'}]}, 'PUT')
    # 3 단계 저장 → 개정 이력 → 되돌리기
    a.j(f'/api/versions/{vid}/steps', {'steps': [{'start': 0, 'end': 3, 'title': '보호구 착용', 'note': '안전모와 안전화', 'warn': '턱끈 고정'}, {'start': 3, 'end': 7, 'title': '안전대 체결', 'note': '', 'warn': ''}]}, 'PUT')
    a.j(f'/api/versions/{vid}/steps', {'steps': [{'start': 0, 'end': 7, 'title': '잘못 고친 단계'}]}, 'PUT')
    rev = a.j(f'/api/versions/{vid}/revisions')['rows']; ok(any(r['kind'] == 'steps' for r in rev), 'revision kept')
    a.j(f"/api/revisions/{[r for r in rev if r['kind'] == 'steps'][0]['id']}/restore", {})
    ok([x['title'] for x in a.j(f'/api/manuals/{mid}')['steps']] == ['보호구 착용', '안전대 체결'], 'restored')
    # 4 도형 저장도 이력
    a.j(f'/api/versions/{vid}/annotations', {'rows': [{'start': 0, 'end': 3, 'kind': 'rect', 'x': .1, 'y': .1, 'w': .3, 'h': .2, 'color': '#e8531b', 'text': ''}, {'start': 1, 'end': 4, 'kind': 'text', 'x': .1, 'y': .8, 'w': .1, 'h': .1, 'color': '#062540', 'text': '턱끈'}]}, 'PUT')
    a.j(f'/api/versions/{vid}/annotations', {'rows': []}, 'PUT')
    ok(any(r['kind'] == 'annotations' for r in a.j(f'/api/versions/{vid}/revisions')['rows']), 'annotation revision')
    a.j(f"/api/revisions/{[r for r in a.j(f'/api/versions/{vid}/revisions')['rows'] if r['kind'] == 'annotations'][0]['id']}/restore", {})
    # 5 자막 확정 → 자막 고치면 읽기 음성 낡음 표시
    a.j(f'/api/versions/{vid}/subs', {'lang': 'ko', 'confirm': True, 'subs': [{'start': 0, 'end': 3, 'text': '안전모를 쓰고 턱끈을 맨다'}, {'start': 3, 'end': 7, 'text': '안전대를 난간에 건다'}]}, 'PUT')
    sys.path.insert(0, B)
    import sqlite3
    db = sqlite3.connect(os.path.join(tmp, 'app.db')); db.execute("insert or replace into narrations(version_id,lang,file,stale) values(?,?,?,0)", (vid, 'ko', 'x.m4a')); db.commit()
    ok(a.j(f'/api/manuals/{mid}')['narrations'] == ['ko'], 'narration listed')
    a.j(f'/api/versions/{vid}/subs', {'lang': 'ko', 'subs': [{'start': 0, 'end': 3, 'text': '바뀐 자막'}]}, 'PUT')
    ok(a.j(f'/api/manuals/{mid}')['narrations'] == [], 'stale narration hidden')
    a.j(f'/api/versions/{vid}/subs', {'lang': 'ko', 'confirm': True, 'subs': [{'start': 0, 'end': 3, 'text': '안전모를 쓰고 턱끈을 맨다'}, {'start': 3, 'end': 7, 'text': '안전대를 난간에 건다'}]}, 'PUT')
    db.execute('delete from narrations where version_id=?', (vid,)); db.commit()
    # 6 단계 글 번역(손으로 고친 번역 저장 + AI)
    a.j(f'/api/versions/{vid}/steps/i18n', {'lang': 'vi', 'steps': [{'ord': 0, 'title': 'Đeo đồ bảo hộ', 'note': 'Mũ và giày bảo hộ', 'warn': 'Cài quai mũ'}, {'ord': 1, 'title': 'Móc dây an toàn', 'note': '', 'warn': ''}]}, 'PUT')
    t = w1.j(f'/api/versions/{vid}/steps?lang=vi', want=404)  # 공개 전에는 근로자가 못 본다
    if AI:
        a.j(f'/api/versions/{vid}/steps/translate', {'lang': 'en'}); j = wait(a, vid, 'steps-en'); ok(j['state'] == 'done', f'steps translate {j}')
        en = a.j(f'/api/versions/{vid}/steps?lang=en')['steps']; ok(all(x['title'] and x['title'] != '보호구 착용' for x in en), f'en steps {en}')
    # 7 단계 연결 확인 테스트 → 응시 기록·단계별 결과
    a.j(f'/api/manuals/{mid}/quiz', {'quiz': [{'question': '안전모 턱끈은?', 'options': ['맨다', '안 맨다'], 'answer': 0, 'step_ord': 0}, {'question': '안전대는 어디에?', 'options': ['난간', '바닥'], 'answer': 0, 'step_ord': 1}]}, 'PUT')
    a.j(f'/api/manuals/{mid}', {'status': 'published', 'scope': '골조팀'}, 'PUT')
    t = w1.j(f'/api/versions/{vid}/steps?lang=vi'); ok(t['steps'][0]['title'] == 'Đeo đồ bảo hộ', 'worker sees own language steps')
    w2.j(f'/api/manuals/{mid}', want=404)
    qz = w1.j(f'/api/manuals/{mid}')['quiz']; ok([z['step_ord'] for z in qz] == [0, 1] and 'answer' not in qz[0], 'quiz step link')
    w1.j(f'/api/versions/{vid}/progress', {'pct': 100})
    sig = 'data:image/png;base64,' + __import__('base64').b64encode(PNG).decode()
    r = w1.j(f'/api/manuals/{mid}/complete', {'answers': {str(qz[0]['id']): 0, str(qz[1]['id']): 1}, 'signature': sig}); ok(not r['passed'] and r['steps'] == {'0': 100, '1': 0}, f'per-step result {r}')
    r = w1.j(f'/api/manuals/{mid}/complete', {'answers': {str(qz[0]['id']): 0, str(qz[1]['id']): 0}, 'signature': sig}); ok(r['passed'], 'pass second try')
    ok(db.execute('select count(*) from quiz_attempts where manual_id=?', (mid,)).fetchone()[0] == 2, 'attempts stored')
    # 8 그림: 근로자는 볼 수 있는 매뉴얼에 쓰인 그림만
    img = a.j('/api/images', raw=PNG)['image']
    dm = a.j('/api/manuals', {'title': '문서 매뉴얼', 'kind': 'doc'})['id']; dv = a.j(f'/api/manuals/{dm}')['current_version']
    a.j(f'/api/versions/{dv}/steps', {'steps': [{'title': '그림 단계', 'image': img}]}, 'PUT')
    w1.j(f'/api/images/{img}', want=404)
    a.j(f'/api/manuals/{dm}', {'status': 'published'}, 'PUT')
    c, b, _ = w1.r(f'/api/images/{img}'); ok(c == 200 and b[:4] == b'\x89PNG', 'image after publish')
    other = a.j('/api/images', raw=PNG)['image']; w1.j(f'/api/images/{other}', want=404)
    # 9 폴더(여러 단계)
    f1 = a.j('/api/folders', {'name': '프레스 공정'})['id']; f2 = a.j('/api/folders', {'name': '불량', 'parent_id': f1})['id']; f3 = a.j('/api/folders', {'name': '원인·대책', 'parent_id': f2})['id']
    a.j(f'/api/folders/{f1}', {'parent_id': f3}, 'PUT', want=400)
    a.j(f'/api/manuals/{mid}/folder', {'folder_id': f3}, 'PUT'); ok(a.j(f'/api/manuals/{mid}')['folder_id'] == f3, 'manual in folder')
    a.j(f'/api/folders/{f3}', method='DELETE'); ok(a.j(f'/api/manuals/{mid}')['folder_id'] == f2, 'folder delete moves up')
    # 10 과정 편집·진행 리포트·근로자 노출
    cid = a.j('/api/courses', {'title': '신규 입문', 'manual_ids': [mid]})['id']
    a.j(f'/api/courses/{cid}', {'title': '신규 근로자 입문', 'manual_ids': [dm, mid]}, 'PUT')
    ok([i['id'] for i in a.j('/api/courses')['courses'][0]['items']] == [dm, mid], 'course reorder')
    a.j(f'/api/courses/{cid}/assign', {'user_ids': [uid['w1'], uid['w2']]})
    rp = a.j(f'/api/courses/{cid}/report'); ok(len(rp['rows']) == 2 and [r for r in rp['rows'] if r['name'] == '김근로'][0]['cells'][1] == 'done', f'course report {rp}')
    c, b, _ = a.r(f'/api/courses/{cid}/report.xlsx'); ok(c == 200 and b[:2] == b'PK', 'course xlsx')
    dd = a.j('/api/manuals', {'title': '작성 중', 'kind': 'doc'})['id']; a.j(f'/api/courses/{cid}', {'manual_ids': [dm, mid, dd]}, 'PUT')
    ok([i['id'] for i in w2.j('/api/courses')['courses'][0]['items']] == [dm, mid], 'worker course hides unpublished manual')
    ok([i['id'] for i in a.j('/api/courses')['courses'][0]['items']] == [dm, mid, dd], 'manager sees all')
    # 11 스킬 고치기·지우기
    sk = a.j('/api/skills', {'name': '비계', 'manual_ids': [mid]})['id']; a.j(f'/api/skills/{sk}', {'name': '시스템비계 조립', 'manual_ids': [mid, dm]}, 'PUT')
    ok(a.j('/api/skills')['skills'][0]['name'] == '시스템비계 조립', 'skill edit'); a.j(f'/api/skills/{sk}', method='DELETE'); ok(a.j('/api/skills')['skills'] == [], 'skill delete')
    # 12 승인 필수 배포: 새 버전은 검토로, 승인 끝나야 공개
    a.j('/api/settings/policy', {'approval_required': True}, 'PUT')
    a.j(f'/api/manuals/{dm}/docversion', {'reason': '내용 보완'}); ok(a.j(f'/api/manuals/{dm}')['status'] == 'review', 'new version needs approval')
    a.j(f'/api/manuals/{dm}', {'status': 'published'}, 'PUT', want=400)
    a.j(f'/api/manuals/{dm}/approval', {'approver_ids': [uid['mgr']]})
    ap = m_.j('/api/approvals')['rows'][0]; m_.j(f"/api/approvals/{ap['id']}", {'ok': False, 'comment': '그림 보완'})
    a.j(f'/api/manuals/{dm}', {'status': 'published'}, 'PUT', want=400)
    a.j(f'/api/manuals/{dm}/approval', {'approver_ids': [uid['mgr']]})
    ap = m_.j('/api/approvals')['rows'][0]; ok(m_.j(f"/api/approvals/{ap['id']}", {'ok': True})['published'], 'approved publishes')
    a.j('/api/settings/policy', {'approval_required': False}, 'PUT')
    # 13 세부 권한: 관리자에게서 매뉴얼 편집·보고서를 막는다
    a.j(f"/api/users/{uid['mgr']}/perms", {'denied': ['manual_edit', 'reports']}, 'PUT')
    m_.j('/api/manuals', {'title': 'x'}, want=403); m_.j('/api/usage', want=403); m_.j('/api/report.pdf', want=403)
    m_.j('/api/manuals'); m_.j('/api/approvals')
    a.j(f"/api/users/{uid['mgr']}/perms", {'denied': []}, 'PUT'); m_.j('/api/usage')
    # 14 도입 관리
    a.j('/api/onboarding/goals', {'title': '교육 이수 늘리기', 'metric': '이수 건수', 'target': '50'})
    a.j('/api/onboarding/plan', {'week': 14, 'title': 'x'}, want=400)
    pid = a.j('/api/onboarding/plan', {'week': 2, 'title': '골조팀 비계 매뉴얼 배포', 'priority': '상'})['id']; a.j(f'/api/onboarding/plan/{pid}', {'status': 'done'}, 'PUT')
    a.j('/api/onboarding/meetings', {'day': '2026-11-10', 'kind': '정기 점검', 'attendees': '대표, 공무팀', 'notes': '이수율 점검', 'actions': '설비팀 매뉴얼 추가\n점검표 항목 보완'})
    ob = a.j('/api/onboarding'); ok(ob['done_pct'] == 100 and ob['live']['이수 건수'] >= 1 and len(ob['meetings']) == 1, f'onboarding {ob["live"]}')
    ok(sum(1 for t in a.j('/api/tasks')['tasks'] if t['title'].startswith('[회의]')) == 2, 'meeting actions -> tasks')
    # 15 보고서 PDF·엑셀
    w1.j('/api/records', {'kind': 'hazard', 'data': {'title': '단부 난간 해체', 'body': 'B동'}})
    c, b, hd = a.r('/api/report.pdf?from=2026-01-01&to=2030-12-31'); ok(c == 200 and b[:5] == b'%PDF-' and len(b) > 3000, f'report pdf {c} {len(b)}')
    from pypdf import PdfReader
    txt = ''.join(p.extract_text() for p in PdfReader(io.BytesIO(b)).pages); ok('교육 이수' in txt and '김근로' in txt and '단부 난간 해체' in txt, 'report pdf content')
    c, b, _ = a.r('/api/report.xlsx?from=2026-01-01&to=2030-12-31&sections=edu,records'); ok(c == 200 and b[:2] == b'PK', 'report xlsx')
    w1.j('/api/report.pdf', want=403)
    # 16 영상 내보내기(자막·도형·단계 제목을 그려 넣음)
    a.j(f'/api/versions/{vid}/export', {'lang': 'ko'}); j = wait(a, vid, 'export-ko', 600); ok(j['state'] == 'done', f'export {j}')
    c, b, _ = a.r(f'/api/versions/{vid}/export.mp4?lang=ko'); ok(c == 200 and b[4:8] == b'ftyp' and len(b) > 10000, 'export mp4')
    # 17 PDF 작업표준서 → 새 매뉴얼 / 과정 (AI)
    if AI and os.path.exists(PK):
        pdf = open(PK, 'rb').read()
        r = a.j('/api/ai/manual', raw=pdf, headers={'X-Name': urllib.request.quote('위험작업 점검')}); ok(r['steps'] >= 3, f'ai manual {r}')
        ok(a.j(f"/api/manuals/{r['id']}")['kind'] == 'doc', 'ai manual doc')
        tk = a.j('/api/ai/course', raw=pdf, headers={'X-Name': urllib.request.quote('위험작업 과정')})['token']
        for _ in range(1800):
            r = a.j('/api/ai/course/' + tk)
            if r['state'] != 'running':
                break
            time.sleep(1)
        ok(r['state'] == 'done' and len(r['manual_ids']) >= 1, f'ai course {r}')
        ok(any(c['id'] == r['course_id'] and len(c['items']) == len(r['manual_ids']) for c in a.j('/api/courses')['courses']), 'ai course items')
    # 18 접수 관리도 IP 제한, HSTS
    c, b, hd = a.r('/api/me'); ok('Strict-Transport-Security' not in hd, 'no HSTS on http dev')
    print(f'PASS {n} checks')
finally:
    srv.kill()
