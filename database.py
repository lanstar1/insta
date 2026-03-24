"""
LANstar Instagram Automation - Database Layer
SQLite (로컬) / PostgreSQL (Render) 듀얼 지원
투명한 래퍼로 main.py가 SQLite 문법 그대로 사용 가능
"""
import sqlite3
import json
import os
import re
from datetime import datetime

# ─── DB 설정 ───
DATABASE_URL = os.environ.get("DATABASE_URL", "")
USE_PG = DATABASE_URL.startswith("postgres")

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "insta_agent.db")
VIDEOS_JSON = os.path.join(os.path.dirname(__file__), "data", "lanstar_videos.json")

# PostgreSQL 연결
if USE_PG:
    try:
        import psycopg2
        import psycopg2.extras
        HAS_PG = True
    except ImportError:
        HAS_PG = False
        USE_PG = False
else:
    HAS_PG = False


# ═══════════════════════════════════════════
# PostgreSQL ↔ SQLite 투명 래퍼
# main.py가 ?플레이스홀더, dict(row), lastrowid를 그대로 사용 가능
# ═══════════════════════════════════════════

class PGCursorWrapper:
    """PostgreSQL 커서를 SQLite 커서처럼 사용할 수 있게 래핑"""

    def __init__(self, real_cursor):
        self._cursor = real_cursor
        self._lastrowid = None
        self._description = None

    @property
    def lastrowid(self):
        return self._lastrowid

    @property
    def description(self):
        return self._cursor.description

    @property
    def rowcount(self):
        return self._cursor.rowcount

    def _convert_sql(self, sql):
        """SQLite SQL → PostgreSQL SQL 변환"""
        # ? → %s (문자열 리터럴 안의 ?는 건드리지 않기 위해 간단 변환)
        converted = sql.replace("?", "%s")
        # INSERT OR IGNORE → INSERT ... ON CONFLICT DO NOTHING
        converted = converted.replace("INSERT OR IGNORE", "INSERT")
        # CAST(AVG(...) AS INTEGER) → PostgreSQL도 지원하므로 그대로
        return converted

    def execute(self, sql, params=None):
        converted = self._convert_sql(sql)

        # INSERT 문에 RETURNING id 추가 (lastrowid 지원)
        is_insert = converted.strip().upper().startswith("INSERT")
        if is_insert and "RETURNING" not in converted.upper():
            converted = converted.rstrip().rstrip(";") + " RETURNING id"

        if params:
            self._cursor.execute(converted, params)
        else:
            self._cursor.execute(converted)

        # lastrowid 추출
        if is_insert:
            try:
                row = self._cursor.fetchone()
                if row:
                    self._lastrowid = row[0] if isinstance(row, tuple) else row.get("id")
            except Exception:
                self._lastrowid = None

    def executemany(self, sql, params_list):
        converted = self._convert_sql(sql)
        for params in params_list:
            if params:
                self._cursor.execute(converted, params)
            else:
                self._cursor.execute(converted)

    def fetchone(self):
        row = self._cursor.fetchone()
        if row is None:
            return None
        if isinstance(row, tuple) and self._cursor.description:
            cols = [d[0] for d in self._cursor.description]
            return DictRow(cols, row)
        return row

    def fetchall(self):
        rows = self._cursor.fetchall()
        if not rows:
            return []
        if isinstance(rows[0], tuple) and self._cursor.description:
            cols = [d[0] for d in self._cursor.description]
            return [DictRow(cols, r) for r in rows]
        return rows


class DictRow:
    """dict처럼도, tuple처럼도 접근 가능한 Row (SQLite Row 호환)"""

    def __init__(self, columns, values):
        self._columns = columns
        self._values = values
        self._dict = dict(zip(columns, values))

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._values[key]
        return self._dict[key]

    def __contains__(self, key):
        return key in self._dict

    def __iter__(self):
        return iter(self._columns)

    def __len__(self):
        return len(self._columns)

    def keys(self):
        return self._columns

    def values(self):
        return self._values

    def items(self):
        return self._dict.items()

    def get(self, key, default=None):
        return self._dict.get(key, default)


class PGConnectionWrapper:
    """PostgreSQL 커넥션을 SQLite 커넥션처럼 사용"""

    def __init__(self, real_conn):
        self._conn = real_conn

    def cursor(self):
        return PGCursorWrapper(self._conn.cursor())

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()

    def execute(self, sql, params=None):
        c = self.cursor()
        c.execute(sql, params)
        return c


def get_db():
    """DB 연결 (PostgreSQL 또는 SQLite) — 투명 래퍼 반환"""
    if USE_PG and HAS_PG:
        db_url = DATABASE_URL.replace("postgres://", "postgresql://", 1)
        conn = psycopg2.connect(db_url)
        conn.autocommit = False
        return PGConnectionWrapper(conn)
    else:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn


# ═══════════════════════════════════════════
# 초기화
# ═══════════════════════════════════════════

def init_db():
    conn = get_db()
    c = conn.cursor()

    if USE_PG:
        # PostgreSQL DDL
        c._cursor.execute("""
        CREATE TABLE IF NOT EXISTS videos (
            id SERIAL PRIMARY KEY,
            title TEXT NOT NULL,
            url TEXT UNIQUE NOT NULL,
            video_id TEXT,
            views_text TEXT,
            views_num INTEGER DEFAULT 0,
            upload_date TEXT,
            duration TEXT,
            topic TEXT,
            summary TEXT,
            transcript TEXT,
            transcript_analysis TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )""")

        c._cursor.execute("""
        CREATE TABLE IF NOT EXISTS content_plans (
            id SERIAL PRIMARY KEY,
            video_id INTEGER REFERENCES videos(id),
            content_type TEXT NOT NULL,
            reels_style TEXT,
            status TEXT DEFAULT 'idea',
            title TEXT,
            hook_text TEXT,
            target_duration INTEGER DEFAULT 25,
            caption TEXT,
            script_json TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )""")

        c._cursor.execute("""
        CREATE TABLE IF NOT EXISTS script_scenes (
            id SERIAL PRIMARY KEY,
            plan_id INTEGER REFERENCES content_plans(id) ON DELETE CASCADE,
            scene_order INTEGER NOT NULL,
            scene_type TEXT DEFAULT 'normal',
            duration_sec REAL DEFAULT 2.0,
            narration TEXT,
            visual_desc TEXT,
            text_overlay TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )""")

        c._cursor.execute("""
        CREATE TABLE IF NOT EXISTS tempo_rules (
            id SERIAL PRIMARY KEY,
            content_type TEXT NOT NULL,
            reels_style TEXT,
            rule_name TEXT NOT NULL,
            rule_value TEXT NOT NULL,
            description TEXT
        )""")

        c._cursor.execute("""
        CREATE TABLE IF NOT EXISTS schedules (
            id SERIAL PRIMARY KEY,
            plan_id INTEGER REFERENCES content_plans(id) ON DELETE CASCADE,
            scheduled_at TEXT NOT NULL,
            status TEXT DEFAULT 'scheduled',
            ig_media_id TEXT,
            error_message TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )""")

    else:
        # SQLite DDL
        c.execute("""
        CREATE TABLE IF NOT EXISTS videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            url TEXT UNIQUE NOT NULL,
            video_id TEXT,
            views_text TEXT,
            views_num INTEGER DEFAULT 0,
            upload_date TEXT,
            duration TEXT,
            topic TEXT,
            summary TEXT,
            transcript TEXT,
            transcript_analysis TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )""")

        c.execute("""
        CREATE TABLE IF NOT EXISTS content_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id INTEGER REFERENCES videos(id),
            content_type TEXT NOT NULL CHECK(content_type IN ('reels','card_news','story')),
            reels_style TEXT CHECK(reels_style IN ('kinetic_typo','before_after','pov_chat','cartoon')),
            status TEXT DEFAULT 'idea' CHECK(status IN ('idea','scripting','editing','media_gen','compositing','review','scheduled','published')),
            title TEXT,
            hook_text TEXT,
            target_duration INTEGER DEFAULT 25,
            caption TEXT,
            script_json TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        )""")

        c.execute("""
        CREATE TABLE IF NOT EXISTS script_scenes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_id INTEGER REFERENCES content_plans(id) ON DELETE CASCADE,
            scene_order INTEGER NOT NULL,
            scene_type TEXT DEFAULT 'normal' CHECK(scene_type IN ('hook','normal','result','cta','cover','comparison','quiz','poll','alert')),
            duration_sec REAL DEFAULT 2.0,
            narration TEXT,
            visual_desc TEXT,
            text_overlay TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )""")

        c.execute("""
        CREATE TABLE IF NOT EXISTS tempo_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content_type TEXT NOT NULL,
            reels_style TEXT,
            rule_name TEXT NOT NULL,
            rule_value TEXT NOT NULL,
            description TEXT
        )""")

        c.execute("""
        CREATE TABLE IF NOT EXISTS schedules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_id INTEGER REFERENCES content_plans(id) ON DELETE CASCADE,
            scheduled_at TEXT NOT NULL,
            status TEXT DEFAULT 'scheduled' CHECK(status IN ('scheduled','publishing','published','failed','cancelled')),
            ig_media_id TEXT,
            error_message TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )""")

    conn.commit()

    # 마이그레이션: 기존 videos 테이블에 transcript 컬럼 추가
    _migrate_add_transcript(conn)

    # 기본 템포 규칙 삽입
    _check_and_seed(conn)

    conn.close()
    db_type = "PostgreSQL" if USE_PG else f"SQLite ({DB_PATH})"
    print(f"[DB] Initialized: {db_type}")


def _migrate_add_transcript(conn):
    """기존 videos 테이블에 transcript/transcript_analysis 컬럼 추가 (마이그레이션)"""
    try:
        if USE_PG:
            c = conn.cursor()
            c._cursor.execute("ALTER TABLE videos ADD COLUMN IF NOT EXISTS transcript TEXT")
            c._cursor.execute("ALTER TABLE videos ADD COLUMN IF NOT EXISTS transcript_analysis TEXT")
        else:
            c = conn.cursor()
            # SQLite: pragma로 컬럼 존재 확인
            c.execute("PRAGMA table_info(videos)")
            cols = [row[1] if isinstance(row, tuple) else row["name"] for row in c.fetchall()]
            if "transcript" not in cols:
                c.execute("ALTER TABLE videos ADD COLUMN transcript TEXT")
            if "transcript_analysis" not in cols:
                c.execute("ALTER TABLE videos ADD COLUMN transcript_analysis TEXT")
        conn.commit()
    except Exception as e:
        print(f"[DB] Migration note: {e}")


def _check_and_seed(conn):
    """템포 규칙과 비디오 데이터 시딩"""
    c = conn.cursor()

    # 템포 규칙
    if USE_PG:
        c._cursor.execute("SELECT COUNT(*) as cnt FROM tempo_rules")
        row = c._cursor.fetchone()
        count = row[0]
    else:
        c.execute("SELECT COUNT(*) FROM tempo_rules")
        row = c.fetchone()
        count = row[0]

    if count == 0:
        _insert_default_tempo_rules(conn)

    # YouTube JSON 로드
    if USE_PG:
        c._cursor.execute("SELECT COUNT(*) as cnt FROM videos")
        row = c._cursor.fetchone()
        count = row[0]
    else:
        c.execute("SELECT COUNT(*) FROM videos")
        row = c.fetchone()
        count = row[0]

    if count == 0:
        _load_videos_from_json(conn)


def _insert_default_tempo_rules(conn):
    rules = [
        ('reels', None, 'total_duration', '20-35', '릴스 전체 길이 (초)'),
        ('reels', None, 'hook_duration', '1.5-3', '후킹 씬 길이 (초) - 결과/임팩트 먼저'),
        ('reels', None, 'cut_duration', '1-2', '일반 컷 길이 (초)'),
        ('reels', None, 'cta_duration', '3-5', 'CTA 씬 길이 (초)'),
        ('reels', None, 'tts_speed', '280-320', 'TTS 분당 글자수'),
        ('reels', None, 'hook_structure', 'result_first', '결과를 먼저 보여주고 방법을 나중에'),
        ('reels', 'kinetic_typo', 'text_size', 'large', '화면 지배하는 큰 텍스트'),
        ('reels', 'kinetic_typo', 'text_animation', 'pop_slide', '텍스트 팝/슬라이드 등장'),
        ('reels', 'kinetic_typo', 'bg_type', 'product_broll', '실사 제품 영상 배경'),
        ('reels', 'kinetic_typo', 'ratio', '60', '전체 릴스 중 비율 (%)'),
        ('reels', 'before_after', 'layout', 'split_vertical', '상하 분할 화면'),
        ('reels', 'before_after', 'comparison', 'number_bar', '숫자 + 바 그래프 비교'),
        ('reels', 'before_after', 'ratio', '20', '전체 릴스 중 비율 (%)'),
        ('reels', 'pov_chat', 'format', 'kakao_chat', '카카오톡 대화 형식'),
        ('reels', 'pov_chat', 'tone', 'casual_humor', '반말 + 유머 + ㅋㅋ'),
        ('reels', 'pov_chat', 'ratio', '20', '전체 릴스 중 비율 (%)'),
        ('card_news', None, 'slide_count', '5-8', '슬라이드 수'),
        ('card_news', None, 'text_per_slide', 'minimal', '텍스트 최소화, 이미지 중심'),
        ('card_news', None, 'cover_style', 'question_hook', '질문형 커버'),
        ('card_news', None, 'last_slide', 'cta_save', '마지막 장: 저장/CTA'),
        ('story', None, 'types', 'quiz,poll,alert', '퀴즈/투표/영상알림'),
        ('story', None, 'text_amount', 'very_minimal', '텍스트 극도로 최소화'),
        ('story', None, 'bg_style', 'photo_based', '실사 이미지 배경'),
        ('all', None, 'tone', 'casual_friendly', 'IT 잘 아는 친한 형 톤'),
        ('all', None, 'forbidden_words', '~하겠습니다,~드리겠습니다,안녕하세요 여러분,본 콘텐츠에서는', 'AI 투 금지어'),
        ('all', None, 'emoji_use', 'moderate', '이모지 적절히 사용'),
        ('all', None, 'humor_style', 'relatable_meme', '공감형 유머 + 밈'),
    ]

    if USE_PG:
        c = conn.cursor()
        for r in rules:
            c._cursor.execute(
                "INSERT INTO tempo_rules (content_type, reels_style, rule_name, rule_value, description) VALUES (%s,%s,%s,%s,%s)",
                r
            )
    else:
        c = conn.cursor()
        c.executemany(
            "INSERT INTO tempo_rules (content_type, reels_style, rule_name, rule_value, description) VALUES (?,?,?,?,?)",
            rules
        )
    conn.commit()


def _load_videos_from_json(conn):
    if not os.path.exists(VIDEOS_JSON):
        print(f"[DB] Video JSON not found: {VIDEOS_JSON}")
        return

    with open(VIDEOS_JSON, 'r', encoding='utf-8') as f:
        data = json.load(f)

    videos = data.get("영상목록", [])
    c = conn.cursor()

    for v in videos:
        url = v.get("URL", "")
        vid = url.split("v=")[-1] if "v=" in url else ""
        params = (
            v.get("제목", ""), url, vid,
            v.get("조회수", ""), v.get("조회수_숫자", 0),
            v.get("업로드일", ""), v.get("영상길이", ""),
            v.get("주제", ""), v.get("핵심내용", "")
        )

        if USE_PG:
            c._cursor.execute("""
                INSERT INTO videos (title, url, video_id, views_text, views_num, upload_date, duration, topic, summary)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (url) DO NOTHING
            """, params)
        else:
            c.execute("""
                INSERT OR IGNORE INTO videos (title, url, video_id, views_text, views_num, upload_date, duration, topic, summary)
                VALUES (?,?,?,?,?,?,?,?,?)
            """, params)

    conn.commit()
    print(f"[DB] Loaded {len(videos)} videos from JSON")
