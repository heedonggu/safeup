"""SQLite 연결과 스키마. 스레드 서버라 잠금 하나로 직렬화한다."""
import hashlib, os, sqlite3, threading

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get('DATA_DIR') or os.path.join(BASE, 'data')
VIDEOS = os.path.join(DATA, 'videos')
os.makedirs(VIDEOS, exist_ok=True)
DB = sqlite3.connect(os.path.join(DATA, 'app.db'), check_same_thread=False)
DB.row_factory = sqlite3.Row
DB.execute('pragma journal_mode=wal')
DB.execute('pragma foreign_keys=on')
LOCK = threading.RLock()

DB.executescript('''
create table if not exists leads(id integer primary key, created text, kind text, data text, status text default 'new', ip text);
create table if not exists users(id integer primary key, login text unique not null, name text not null, salt text, hash text,
  role text not null default 'worker', dept text default '', site text default '', lang text default 'ko',
  active int default 1, must_change int default 0, sv int default 0, created text default current_timestamp);
create table if not exists manuals(id integer primary key, title text not null, category text default '', dept text default '',
  owner_id int references users(id), status text default 'draft', current_version int, standard_version int, required int default 1,
  created text default current_timestamp);
create table if not exists versions(id integer primary key, manual_id int not null references manuals(id), no int not null, file text,
  thumb text, reason text default '', author_id int, state text default 'processing', error text default '', duration real default 0,
  created text default current_timestamp);
create table if not exists steps(id integer primary key, version_id int not null references versions(id), ord int, start real, end real,
  title text, note text default '', warn text default '');
create table if not exists subs(id integer primary key, version_id int not null references versions(id), lang text not null, ord int,
  start real, end real, text text, confirmed int default 0);
create table if not exists subjobs(version_id int, lang text, state text, error text default '', primary key(version_id, lang));
create table if not exists glossary(id integer primary key, term text unique, replace_with text);
create table if not exists assigns(id integer primary key, manual_id int not null references manuals(id), user_id int not null references users(id),
  due text default '', created text default current_timestamp, unique(manual_id, user_id));
create table if not exists views(user_id int, version_id int, pct real default 0, lang text default 'ko', updated text default current_timestamp,
  primary key(user_id, version_id));
create table if not exists quiz(id integer primary key, manual_id int not null references manuals(id), ord int, question text, options text, answer int);
create table if not exists completions(id integer primary key, manual_id int, version_id int, user_id int, score int, lang text, signature text,
  created text default current_timestamp, unique(version_id, user_id));
create table if not exists courses(id integer primary key, title text not null, created text default current_timestamp);
create table if not exists course_items(course_id int references courses(id), manual_id int references manuals(id), ord int, primary key(course_id, manual_id));
create table if not exists compare_notes(id integer primary key, a_version int, b_version int, t real, memo text, user_id int, created text default current_timestamp);
create table if not exists tasks(id integer primary key, title text not null, manual_id int, assignee_id int, due text default '', status text default 'open',
  note_id int, created text default current_timestamp);
create table if not exists forms(id integer primary key, title text not null, site text default '', schema text not null, owner_id int, active int default 1,
  created text default current_timestamp);
create table if not exists submissions(id integer primary key, form_id int references forms(id), user_id int, vals text, abnormal int default 0,
  created text default current_timestamp);
create table if not exists alerts(id integer primary key, submission_id int, message text, done int default 0, created text default current_timestamp);
create table if not exists obligations(half text, code text, status text default 'todo', memo text default '', checked_by int, checked_at text, primary key(half, code));
create table if not exists records(id integer primary key, kind text not null, data text not null, status text default 'open', user_id int,
  created text default current_timestamp);
create table if not exists audit(id integer primary key, user_id int, action text, target text, ip text, created text default current_timestamp);
create index if not exists i_sub on subs(version_id, lang, ord);
create table if not exists bookmarks(user_id int, manual_id int, created text default current_timestamp, primary key(user_id, manual_id));
create table if not exists plans(id integer primary key, title text not null, owner_id int, due text default '', status text default 'todo', manual_id int, created text default current_timestamp);
create table if not exists approvals(id integer primary key, manual_id int, step int, approver_id int, status text default 'wait', comment text default '', at text, requested_by int, created text default current_timestamp);
create table if not exists skills(id integer primary key, name text not null, category text default '', manual_ids text default '[]', created text default current_timestamp);
create table if not exists evals(id integer primary key, user_id int, skill_id int, level int, kind text default 'eval', evaluator_id int, comment text default '', created text default current_timestamp);
create table if not exists skill_plans(id integer primary key, user_id int, skill_id int, target int, due text default '', created text default current_timestamp, unique(user_id, skill_id));
create table if not exists narrations(version_id int, lang text, file text, primary key(version_id, lang));
create table if not exists elements(id integer primary key, version_id int, ord int, start real, end real, label text default '');
create table if not exists settings(k text primary key, v text);
create table if not exists bookmarks(user_id int, manual_id int, created text default current_timestamp, primary key(user_id, manual_id));
create table if not exists plans(id integer primary key, title text not null, owner_id int, due text default '', status text default 'todo', manual_id int, created text default current_timestamp);
create table if not exists approvals(id integer primary key, manual_id int, step int, approver_id int, status text default 'wait', comment text default '', at text, requested_by int, created text default current_timestamp);
create table if not exists skills(id integer primary key, name text not null, category text default '', manual_ids text default '[]', created text default current_timestamp);
create table if not exists evals(id integer primary key, user_id int, skill_id int, level int, kind text default 'eval', evaluator_id int, comment text default '', created text default current_timestamp);
create table if not exists skill_plans(id integer primary key, user_id int, skill_id int, target int, due text default '', created text default current_timestamp, unique(user_id, skill_id));
create table if not exists narrations(version_id int, lang text, file text, primary key(version_id, lang));
create table if not exists elements(id integer primary key, version_id int, ord int, start real, end real, label text default '');
create table if not exists settings(k text primary key, v text);
create index if not exists i_stp on steps(version_id, ord);
''')
for t, col, decl in [('manuals', 'tags', "text default ''"), ('manuals', 'scope', "text default ''"), ('manuals', 'kind', "text default 'video'"),
                     ('steps', 'image', "text default ''"), ('users', 'pending', 'int default 0'), ('users', 'totp', "text default ''"),
                     ('submissions', 'status', "text default 'wait'"), ('submissions', 'approver_id', 'int'), ('submissions', 'comment', "text default ''"),
                     ('users', 'email', "text default ''")]:
    if col not in [r[1] for r in DB.execute(f'pragma table_info({t})').fetchall()]:
        DB.execute(f'alter table {t} add column {col} {decl}')
for t, col, decl in [('manuals', 'tags', "text default ''"), ('manuals', 'scope', "text default ''"), ('manuals', 'kind', "text default 'video'"),
                     ('steps', 'image', "text default ''"), ('users', 'pending', 'int default 0'), ('users', 'totp', "text default ''"),
                     ('submissions', 'status', "text default 'wait'"), ('submissions', 'approver_id', 'int'), ('submissions', 'comment', "text default ''"),
                     ('users', 'email', "text default ''")]:
    if col not in [r[1] for r in DB.execute(f'pragma table_info({t})').fetchall()]:
        DB.execute(f'alter table {t} add column {col} {decl}')
DB.commit()


def q(sql, a=()):
    with LOCK:
        return [dict(r) for r in DB.execute(sql, a).fetchall()]


def one(sql, a=()):
    r = q(sql, a)
    return r[0] if r else None


def x(sql, a=()):
    with LOCK:
        c = DB.execute(sql, a)
        DB.commit()
        return c.lastrowid


def many(fn):
    """한 트랜잭션 묶음. fn(DB)가 실패하면 되돌린다."""
    with LOCK:
        try:
            r = fn(DB)
            DB.commit()
            return r
        except Exception:
            DB.rollback()
            raise


def pw_hash(pw, salt):
    return hashlib.pbkdf2_hmac('sha256', pw.encode(), bytes.fromhex(salt), 200_000).hex()
