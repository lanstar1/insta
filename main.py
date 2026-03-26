"""
LANstar Instagram Automation Agent
Phase 1: Foundation + Idea Bank
FastAPI Backend
"""
from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
from typing import Optional, List
import json
import os
import asyncio
import logging
import subprocess
from datetime import datetime

logger = logging.getLogger("insta-agent")

from database import get_db, init_db
from script_engine import generate_script_claude, generate_script_fallback, check_spelling
from media_engine import run_media_pipeline, generate_tts, MEDIA_DIR
from instagram_api import InstagramClient, ScheduleManager
from transcriber import analyze_transcript

app = FastAPI(title="LANstar Insta Agent", version="0.2.0")

# Static files
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# ─── Pydantic Models ───
class ContentPlanCreate(BaseModel):
    video_id: int
    content_type: str  # reels, card_news, story
    reels_style: Optional[str] = None
    title: Optional[str] = None
    hook_text: Optional[str] = None
    target_duration: Optional[int] = 25


class SceneCreate(BaseModel):
    scene_order: int
    scene_type: str = "normal"
    duration_sec: float = 2.0
    narration: Optional[str] = None
    visual_desc: Optional[str] = None
    text_overlay: Optional[str] = None


class PlanUpdate(BaseModel):
    status: Optional[str] = None
    title: Optional[str] = None
    hook_text: Optional[str] = None
    reels_style: Optional[str] = None
    target_duration: Optional[int] = None
    caption: Optional[str] = None


class GenerateScriptRequest(BaseModel):
    plan_id: int
    api_key: Optional[str] = None


class SpellCheckRequest(BaseModel):
    text: str


class SceneBulkUpdate(BaseModel):
    scenes: List[SceneCreate]


class MediaGenerateRequest(BaseModel):
    plan_id: int
    api_keys: Optional[dict] = None  # {elevenlabs, together, openai, minimax, image_provider}


class TTSPreviewRequest(BaseModel):
    text: str
    voice_id: Optional[str] = None
    api_key: Optional[str] = None


class InstagramUploadRequest(BaseModel):
    plan_id: int
    access_token: Optional[str] = None
    ig_user_id: Optional[str] = None
    media_url: Optional[str] = None  # 외부 호스팅된 URL


class ScheduleCreateRequest(BaseModel):
    plan_id: int
    scheduled_at: str  # ISO format


class ScheduleSuggestRequest(BaseModel):
    count: int = 7
    start_date: Optional[str] = None


class AnalyzeRequest(BaseModel):
    api_key: Optional[str] = None


class ManualTranscriptRequest(BaseModel):
    transcript: str
    api_key: Optional[str] = None


# ─── Root ───
@app.head("/")
async def root_head():
    """Render 헬스체크용 HEAD 응답"""
    from fastapi.responses import Response
    return Response(status_code=200)


@app.get("/", response_class=HTMLResponse)
async def root():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


# ─── Videos (Idea Bank) ───
@app.get("/api/videos")
async def get_videos(
    topic: Optional[str] = None,
    search: Optional[str] = None,
    sort: str = "views_desc",
    page: int = 1,
    limit: int = 20
):
    conn = get_db()
    c = conn.cursor()

    where_clauses = []
    params = []

    if topic and topic != "all":
        where_clauses.append("topic = ?")
        params.append(topic)

    if search:
        where_clauses.append("title LIKE ?")
        params.append(f"%{search}%")

    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

    sort_map = {
        "views_desc": "views_num DESC",
        "views_asc": "views_num ASC",
        "title_asc": "title ASC",
        "newest": "id DESC",
        "oldest": "id ASC"
    }
    sort_sql = sort_map.get(sort, "views_num DESC")

    offset = (page - 1) * limit

    # Count
    c.execute(f"SELECT COUNT(*) FROM videos {where_sql}", params)
    total = c.fetchone()[0]

    # Data
    c.execute(f"""
        SELECT v.*,
               (SELECT COUNT(*) FROM content_plans cp WHERE cp.video_id = v.id) as plan_count
        FROM videos v
        {where_sql}
        ORDER BY {sort_sql}
        LIMIT ? OFFSET ?
    """, params + [limit, offset])

    videos = []
    for row in c.fetchall():
        v = dict(row)
        # 목록에서는 전사 텍스트 전체를 보내지 않고 플래그만
        v["transcript"] = "yes" if v.get("transcript") else ""
        v.pop("transcript_analysis", None)
        videos.append(v)
    conn.close()

    return {
        "videos": videos,
        "total": total,
        "page": page,
        "pages": (total + limit - 1) // limit
    }


@app.get("/api/videos/{video_id}")
async def get_video(video_id: int):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM videos WHERE id = ?", (video_id,))
    video = c.fetchone()
    if not video:
        conn.close()
        raise HTTPException(404, "Video not found")

    video = dict(video)

    c.execute("SELECT * FROM content_plans WHERE video_id = ? ORDER BY created_at DESC", (video_id,))
    video["plans"] = [dict(r) for r in c.fetchall()]

    conn.close()
    return video


@app.get("/api/topics")
async def get_topics():
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT topic, COUNT(*) as count,
               SUM(views_num) as total_views,
               CAST(AVG(views_num) AS INTEGER) as avg_views
        FROM videos
        GROUP BY topic
        ORDER BY count DESC
    """)
    topics = [dict(row) for row in c.fetchall()]
    conn.close()
    return topics


@app.get("/api/stats")
async def get_stats():
    conn = get_db()
    c = conn.cursor()

    stats = {}
    c.execute("SELECT COUNT(*) FROM videos")
    stats["total_videos"] = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM content_plans")
    stats["total_plans"] = c.fetchone()[0]

    c.execute("SELECT status, COUNT(*) as cnt FROM content_plans GROUP BY status")
    stats["plan_status"] = {r["status"]: r["cnt"] for r in c.fetchall()}

    c.execute("SELECT content_type, COUNT(*) as cnt FROM content_plans GROUP BY content_type")
    stats["plan_types"] = {r["content_type"]: r["cnt"] for r in c.fetchall()}

    conn.close()
    return stats


# ─── 전사 & 분석 (Transcription & Analysis) ───

@app.post("/api/videos/{video_id}/transcribe-manual")
async def transcribe_manual(video_id: int, req: ManualTranscriptRequest):
    """수동으로 전사 텍스트 입력 (YouTube IP 차단 우회용)"""
    if not req.transcript or not req.transcript.strip():
        return {"status": "error", "error": "전사 텍스트가 비어있습니다."}

    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT * FROM videos WHERE id = ?", (video_id,))
    video = c.fetchone()
    if not video:
        conn.close()
        raise HTTPException(404, "Video not found")

    video = dict(video)
    transcript_text = req.transcript.strip()

    # Claude 분석
    api_key = req.api_key or os.environ.get("ANTHROPIC_API_KEY", "")
    try:
        analysis = await asyncio.to_thread(
            analyze_transcript,
            transcript_text,
            video.get("title", ""),
            video.get("topic", ""),
            api_key
        )
    except Exception as e:
        logger.error(f"[ManualTranscribe] 분석 예외: {e}")
        analysis = {"status": "error", "error": str(e), "engine": "failed"}

    # DB 저장
    analysis_json = json.dumps(analysis, ensure_ascii=False) if analysis else None
    c.execute("UPDATE videos SET transcript = ?, transcript_analysis = ? WHERE id = ?",
              (transcript_text, analysis_json, video_id))
    conn.commit()
    conn.close()

    logger.warning(f"[ManualTranscribe] video_id={video_id} 수동 전사 저장: {len(transcript_text)}자")
    return {
        "status": "ok",
        "transcript": transcript_text,
        "analysis": analysis,
        "word_count": len(transcript_text),
    }


@app.post("/api/videos/{video_id}/analyze")
async def analyze_video(video_id: int, req: AnalyzeRequest = None):
    """이미 전사된 텍스트를 (재)분석"""
    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT * FROM videos WHERE id = ?", (video_id,))
    video = c.fetchone()
    if not video:
        conn.close()
        raise HTTPException(404, "Video not found")

    video = dict(video)
    if not video.get("transcript"):
        conn.close()
        return {"status": "error", "error": "전사 텍스트가 없습니다. 먼저 전사를 실행하세요."}

    api_key = (req.api_key if req else None) or os.environ.get("ANTHROPIC_API_KEY", "")
    analysis = await asyncio.to_thread(
        analyze_transcript,
        video["transcript"],
        video.get("title", ""),
        video.get("topic", ""),
        api_key
    )

    # DB 업데이트
    analysis_json = json.dumps(analysis, ensure_ascii=False)
    c.execute("UPDATE videos SET transcript_analysis = ? WHERE id = ?",
              (analysis_json, video_id))
    conn.commit()
    conn.close()

    return {"status": "ok", "analysis": analysis}


@app.get("/api/videos/{video_id}/transcript")
async def get_video_transcript(video_id: int):
    """전사 텍스트 조회"""
    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT id, title, transcript, transcript_analysis FROM videos WHERE id = ?", (video_id,))
    video = c.fetchone()
    conn.close()

    if not video:
        raise HTTPException(404, "Video not found")

    video = dict(video)
    analysis = None
    if video.get("transcript_analysis"):
        try:
            analysis = json.loads(video["transcript_analysis"])
        except Exception:
            pass

    t = video.get("transcript") or ""
    return {
        "has_transcript": bool(t),
        "transcript": t,
        "analysis": analysis,
        "word_count": len(t),
    }


# ─── Content Plans ───
@app.post("/api/plans")
async def create_plan(plan: ContentPlanCreate):
    conn = get_db()
    c = conn.cursor()

    # Validate video exists
    c.execute("SELECT id, title FROM videos WHERE id = ?", (plan.video_id,))
    video = c.fetchone()
    if not video:
        conn.close()
        raise HTTPException(404, "Video not found")

    title = plan.title or video["title"]

    c.execute("""
        INSERT INTO content_plans (video_id, content_type, reels_style, title, hook_text, target_duration)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (plan.video_id, plan.content_type, plan.reels_style, title, plan.hook_text, plan.target_duration))

    plan_id = c.lastrowid
    conn.commit()
    conn.close()
    return {"id": plan_id, "message": "Plan created"}


@app.get("/api/plans")
async def get_plans(
    status: Optional[str] = None,
    content_type: Optional[str] = None,
    page: int = 1,
    limit: int = 20
):
    conn = get_db()
    c = conn.cursor()

    where_clauses = []
    params = []

    if status:
        where_clauses.append("cp.status = ?")
        params.append(status)
    if content_type:
        where_clauses.append("cp.content_type = ?")
        params.append(content_type)

    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
    offset = (page - 1) * limit

    c.execute(f"SELECT COUNT(*) FROM content_plans cp {where_sql}", params)
    total = c.fetchone()[0]

    c.execute(f"""
        SELECT cp.*, v.title as video_title, v.views_num, v.topic
        FROM content_plans cp
        LEFT JOIN videos v ON cp.video_id = v.id
        {where_sql}
        ORDER BY cp.created_at DESC
        LIMIT ? OFFSET ?
    """, params + [limit, offset])

    plans = [dict(r) for r in c.fetchall()]
    conn.close()

    return {"plans": plans, "total": total, "page": page}


@app.get("/api/plans/{plan_id}")
async def get_plan(plan_id: int):
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        SELECT cp.*, v.title as video_title, v.url as video_url, v.views_num, v.topic, v.summary
        FROM content_plans cp
        LEFT JOIN videos v ON cp.video_id = v.id
        WHERE cp.id = ?
    """, (plan_id,))
    plan = c.fetchone()
    if not plan:
        conn.close()
        raise HTTPException(404, "Plan not found")

    plan = dict(plan)

    c.execute("SELECT * FROM script_scenes WHERE plan_id = ? ORDER BY scene_order", (plan_id,))
    plan["scenes"] = [dict(r) for r in c.fetchall()]

    conn.close()
    return plan


@app.patch("/api/plans/{plan_id}")
async def update_plan(plan_id: int, update: PlanUpdate):
    conn = get_db()
    c = conn.cursor()

    sets = []
    params = []
    for field, val in update.dict(exclude_none=True).items():
        sets.append(f"{field} = ?")
        params.append(val)

    if not sets:
        conn.close()
        raise HTTPException(400, "No fields to update")

    sets.append("updated_at = ?")
    params.append(datetime.now().isoformat())
    params.append(plan_id)

    c.execute(f"UPDATE content_plans SET {', '.join(sets)} WHERE id = ?", params)
    conn.commit()
    conn.close()
    return {"message": "Updated"}


@app.delete("/api/plans/{plan_id}")
async def delete_plan(plan_id: int):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM content_plans WHERE id = ?", (plan_id,))
    conn.commit()
    conn.close()
    return {"message": "Deleted"}


# ─── Scenes ───
@app.post("/api/plans/{plan_id}/scenes")
async def add_scene(plan_id: int, scene: SceneCreate):
    VALID_SCENE_TYPES = {'hook', 'normal', 'result', 'cta', 'cover', 'comparison', 'quiz', 'poll', 'alert'}
    conn = get_db()
    c = conn.cursor()
    scene_type = scene.scene_type if scene.scene_type in VALID_SCENE_TYPES else "normal"
    c.execute("""
        INSERT INTO script_scenes (plan_id, scene_order, scene_type, duration_sec, narration, visual_desc, text_overlay)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (plan_id, scene.scene_order, scene_type, scene.duration_sec,
          scene.narration, scene.visual_desc, scene.text_overlay))
    conn.commit()
    conn.close()
    return {"id": c.lastrowid}


@app.put("/api/scenes/{scene_id}")
async def update_scene(scene_id: int, scene: SceneCreate):
    VALID_SCENE_TYPES = {'hook', 'normal', 'result', 'cta', 'cover', 'comparison', 'quiz', 'poll', 'alert'}
    conn = get_db()
    c = conn.cursor()
    scene_type = scene.scene_type if scene.scene_type in VALID_SCENE_TYPES else "normal"
    c.execute("""
        UPDATE script_scenes SET scene_order=?, scene_type=?, duration_sec=?,
        narration=?, visual_desc=?, text_overlay=? WHERE id=?
    """, (scene.scene_order, scene_type, scene.duration_sec,
          scene.narration, scene.visual_desc, scene.text_overlay, scene_id))
    conn.commit()
    conn.close()
    return {"message": "Updated"}


@app.delete("/api/scenes/{scene_id}")
async def delete_scene(scene_id: int):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM script_scenes WHERE id = ?", (scene_id,))
    conn.commit()
    conn.close()
    return {"message": "Deleted"}


# ─── Script Generation ───
@app.post("/api/generate-script")
async def generate_script(req: GenerateScriptRequest):
    """스크립트 자동 생성 (Claude API 또는 Fallback)"""
    conn = get_db()
    c = conn.cursor()

    # Plan + Video 정보 조회 (전사 텍스트 포함)
    c.execute("""
        SELECT cp.*, v.title as video_title, v.topic, v.summary,
               v.transcript, v.transcript_analysis
        FROM content_plans cp
        LEFT JOIN videos v ON cp.video_id = v.id
        WHERE cp.id = ?
    """, (req.plan_id,))
    plan = c.fetchone()
    if not plan:
        conn.close()
        raise HTTPException(404, "Plan not found")

    plan = dict(plan)

    # 전사 분석 결과 텍스트 변환
    analysis_text = ""
    if plan.get("transcript_analysis"):
        try:
            analysis = json.loads(plan["transcript_analysis"])
            parts = []
            if analysis.get("key_facts"):
                parts.append("핵심 팩트: " + " / ".join(analysis["key_facts"][:5]))
            if analysis.get("hook_candidates"):
                parts.append("후킹 후보: " + " / ".join(analysis["hook_candidates"][:3]))
            if analysis.get("product_names"):
                parts.append("제품/기술: " + ", ".join(analysis["product_names"][:5]))
            if analysis.get("summary"):
                parts.append("요약: " + analysis["summary"])
            analysis_text = "\n".join(parts)
        except Exception:
            pass

    # 스크립트 생성 (전사 텍스트가 있으면 팩트 기반)
    result = generate_script_claude(
        video_title=plan.get("video_title") or plan.get("title", ""),
        video_topic=plan.get("topic", ""),
        video_summary=plan.get("summary", ""),
        content_type=plan["content_type"],
        reels_style=plan.get("reels_style"),
        hook_text=plan.get("hook_text"),
        target_duration=plan.get("target_duration", 25),
        api_key=req.api_key,
        transcript=plan.get("transcript", ""),
        transcript_analysis=analysis_text,
    )

    if "error" in result:
        conn.close()
        return {"status": "fallback", "script": result, "message": result.get("error", "")}

    # 생성된 씬 DB에 저장
    scenes = result.get("scenes") or result.get("slides") or []

    # Story는 flat 구조 → 씬 1개로 변환
    if not scenes and plan["content_type"] == "story":
        scenes = [{
            "scene_order": 1,
            "scene_type": result.get("story_type", "quiz"),
            "duration_sec": 15.0,
            "narration": None,
            "visual_desc": result.get("background_desc", ""),
            "text_overlay": result.get("main_text", "")
        }]

    # 허용된 scene_type 목록 (DB CHECK constraint와 동기화)
    VALID_SCENE_TYPES = {'hook', 'normal', 'result', 'cta', 'cover', 'comparison', 'quiz', 'poll', 'alert'}

    if scenes:
        # 기존 씬 삭제
        c.execute("DELETE FROM script_scenes WHERE plan_id = ?", (req.plan_id,))
        for s in scenes:
            raw_type = s.get("scene_type", "normal")
            scene_type = raw_type if raw_type in VALID_SCENE_TYPES else "normal"
            c.execute("""
                INSERT INTO script_scenes (plan_id, scene_order, scene_type, duration_sec, narration, visual_desc, text_overlay)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                req.plan_id,
                s.get("scene_order", 0),
                scene_type,
                float(s.get("duration_sec", 2.0)),
                s.get("narration"),
                s.get("visual_desc"),
                s.get("text_overlay") or s.get("sub_text")
            ))

    # Plan 상태 업데이트 + hook_text/title/caption/script_json 저장
    updates = ["status = 'scripting'", "updated_at = ?", "script_json = ?"]
    params = [datetime.now().isoformat(), json.dumps(result, ensure_ascii=False)]
    if result.get("hook_text") and not plan.get("hook_text"):
        updates.append("hook_text = ?")
        params.append(result["hook_text"])
    if result.get("title") and not plan.get("title"):
        updates.append("title = ?")
        params.append(result["title"])
    if result.get("caption"):
        updates.append("caption = ?")
        params.append(result["caption"])

    params.append(req.plan_id)
    c.execute(f"UPDATE content_plans SET {', '.join(updates)} WHERE id = ?", params)

    conn.commit()
    conn.close()

    return {"status": "ok", "script": result, "scenes_count": len(scenes)}


@app.post("/api/check-spelling")
async def spelling_check(req: SpellCheckRequest):
    """맞춤법 체크"""
    issues = check_spelling(req.text)
    return {"issues": issues, "text": req.text}


@app.put("/api/plans/{plan_id}/scenes/bulk")
async def bulk_update_scenes(plan_id: int, data: SceneBulkUpdate):
    """씬 일괄 저장 (기존 삭제 후 재생성)"""
    conn = get_db()
    c = conn.cursor()

    # Plan 존재 확인
    c.execute("SELECT id FROM content_plans WHERE id = ?", (plan_id,))
    if not c.fetchone():
        conn.close()
        raise HTTPException(404, "Plan not found")

    # 기존 씬 삭제 후 재생성
    VALID_SCENE_TYPES = {'hook', 'normal', 'result', 'cta', 'cover', 'comparison', 'quiz', 'poll', 'alert'}
    c.execute("DELETE FROM script_scenes WHERE plan_id = ?", (plan_id,))
    for s in data.scenes:
        scene_type = s.scene_type if s.scene_type in VALID_SCENE_TYPES else "normal"
        c.execute("""
            INSERT INTO script_scenes (plan_id, scene_order, scene_type, duration_sec, narration, visual_desc, text_overlay)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (plan_id, s.scene_order, scene_type, s.duration_sec,
              s.narration, s.visual_desc, s.text_overlay))

    # updated_at 갱신
    c.execute("UPDATE content_plans SET updated_at = ? WHERE id = ?",
              (datetime.now().isoformat(), plan_id))

    conn.commit()
    conn.close()
    return {"message": "Scenes saved", "count": len(data.scenes)}


# ─── Media Generation ───
@app.post("/api/generate-media")
async def generate_media(req: MediaGenerateRequest):
    """미디어 파이프라인 실행 (TTS + 이미지 + 영상 + 합성)"""
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        SELECT cp.*, v.title as video_title, v.topic
        FROM content_plans cp
        LEFT JOIN videos v ON cp.video_id = v.id
        WHERE cp.id = ?
    """, (req.plan_id,))
    plan = c.fetchone()
    if not plan:
        conn.close()
        raise HTTPException(404, "Plan not found")
    plan = dict(plan)

    # 씬 가져오기
    c.execute("SELECT * FROM script_scenes WHERE plan_id = ? ORDER BY scene_order", (req.plan_id,))
    scenes = [dict(r) for r in c.fetchall()]

    if not scenes:
        conn.close()
        raise HTTPException(400, "씬이 없습니다. 먼저 스크립트를 생성하세요.")

    # 미디어 파이프라인 실행 (sync → async wrapper)
    logging.info(f"[MediaGen] plan_id={req.plan_id} content_type={plan['content_type']} scenes={len(scenes)}")
    try:
        result = await asyncio.to_thread(
            run_media_pipeline,
            plan_id=req.plan_id,
            content_type=plan["content_type"],
            scenes=scenes,
            api_keys=req.api_keys or {}
        )
    except Exception as e:
        logging.error(f"[MediaGen] pipeline exception: {e}", exc_info=True)
        conn.close()
        return {"error": f"미디어 생성 실패: {str(e)}"}

    logging.info(f"[MediaGen] result: {json.dumps(result, ensure_ascii=False, default=str)[:500]}")

    # 상태 업데이트
    if result.get("status") in ("ok", "placeholder"):
        c.execute("UPDATE content_plans SET status = 'media_gen', updated_at = ? WHERE id = ?",
                  (datetime.now().isoformat(), req.plan_id))
        conn.commit()

    conn.close()
    return result


@app.post("/api/tts-preview")
async def tts_preview(req: TTSPreviewRequest):
    """TTS 미리듣기"""
    import tempfile
    preview_path = os.path.join(MEDIA_DIR, "tts_preview.wav")
    result = generate_tts(req.text, preview_path, req.voice_id, req.api_key)
    return result


@app.get("/api/media/{plan_id}/status")
async def get_media_status(plan_id: int):
    """미디어 생성 상태 확인"""
    plan_dir = os.path.join(MEDIA_DIR, f"plan_{plan_id}")
    if not os.path.exists(plan_dir):
        return {"status": "not_started", "files": []}

    files = []
    for root, dirs, fnames in os.walk(plan_dir):
        for fn in fnames:
            fp = os.path.join(root, fn)
            files.append({
                "name": fn,
                "path": fp,
                "size": os.path.getsize(fp),
                "type": fn.split('.')[-1] if '.' in fn else 'unknown'
            })

    return {"status": "generated", "files": files, "dir": plan_dir}


# ─── Media Debug ───
@app.get("/api/debug/media-test/{plan_id}")
async def debug_media_test(plan_id: int):
    """미디어 파이프라인 디버그용 - 환경/에러 확인"""
    import shutil
    info = {
        "ffmpeg": shutil.which("ffmpeg") is not None,
        "ffprobe": shutil.which("ffprobe") is not None,
        "media_dir": MEDIA_DIR,
        "media_dir_exists": os.path.exists(MEDIA_DIR),
    }

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM content_plans WHERE id = ?", (plan_id,))
    plan = c.fetchone()
    if plan:
        plan = dict(plan)
        info["plan"] = {"id": plan["id"], "content_type": plan.get("content_type"), "status": plan.get("status")}

    c.execute("SELECT * FROM script_scenes WHERE plan_id = ? ORDER BY scene_order", (plan_id,))
    scenes = [dict(r) for r in c.fetchall()]
    info["scene_count"] = len(scenes)
    if scenes:
        info["first_scene_keys"] = list(scenes[0].keys())
        info["first_scene_preview"] = {k: str(v)[:80] for k, v in scenes[0].items()}

    # env keys check
    info["env_keys"] = {
        "ELEVENLABS_API_KEY": bool(os.environ.get("ELEVENLABS_API_KEY")),
        "TOGETHER_API_KEY": bool(os.environ.get("TOGETHER_API_KEY")),
        "OPENAI_API_KEY": bool(os.environ.get("OPENAI_API_KEY")),
        "MINIMAX_API_KEY": bool(os.environ.get("MINIMAX_API_KEY")),
    }

    # Try quick FFmpeg test
    try:
        proc = subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:s=100x100:d=0.1",
             "-frames:v", "1", os.path.join(MEDIA_DIR, "test.png")],
            capture_output=True, timeout=5
        )
        info["ffmpeg_test"] = "ok" if proc.returncode == 0 else proc.stderr.decode('utf-8', errors='replace')[:300]
    except Exception as e:
        info["ffmpeg_test"] = str(e)

    conn.close()
    return info


# Serve media files
from fastapi.responses import FileResponse as FR

@app.get("/media/{path:path}")
async def serve_media(path: str):
    """미디어 파일 서빙"""
    file_path = os.path.join(MEDIA_DIR, path)
    if not os.path.exists(file_path):
        raise HTTPException(404, "File not found")
    return FR(file_path)


# ─── Instagram Upload ───
@app.post("/api/instagram/upload")
async def instagram_upload(req: InstagramUploadRequest):
    """인스타그램 업로드"""
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        SELECT cp.*, v.title as video_title
        FROM content_plans cp
        LEFT JOIN videos v ON cp.video_id = v.id
        WHERE cp.id = ?
    """, (req.plan_id,))
    plan = c.fetchone()
    if not plan:
        conn.close()
        raise HTTPException(404, "Plan not found")
    plan = dict(plan)

    client = InstagramClient(req.access_token, req.ig_user_id)
    caption = plan.get("caption") or plan.get("title", "")

    if plan["content_type"] == "reels":
        if not req.media_url:
            conn.close()
            return {"error": "릴스 업로드에는 외부 호스팅된 영상 URL이 필요합니다."}
        result = client.upload_reels(req.media_url, caption)

    elif plan["content_type"] == "card_news":
        # 카드뉴스는 이미지 URL 목록 필요
        if not req.media_url:
            conn.close()
            return {"error": "카드뉴스 업로드에는 이미지 URL 목록이 필요합니다."}
        urls = req.media_url.split(",") if isinstance(req.media_url, str) else [req.media_url]
        result = client.upload_carousel(urls, caption)

    elif plan["content_type"] == "story":
        if not req.media_url:
            conn.close()
            return {"error": "스토리 업로드에는 이미지/영상 URL이 필요합니다."}
        result = client.upload_story(image_url=req.media_url)

    else:
        conn.close()
        return {"error": f"Unknown type: {plan['content_type']}"}

    # 상태 업데이트
    if result.get("status") == "ok":
        c.execute("UPDATE content_plans SET status = 'published', updated_at = ? WHERE id = ?",
                  (datetime.now().isoformat(), req.plan_id))
        conn.commit()

    conn.close()
    return result


@app.get("/api/instagram/account")
async def instagram_account(access_token: str = "", ig_user_id: str = ""):
    """인스타그램 계정 정보"""
    client = InstagramClient(access_token, ig_user_id)
    return client.get_account_info()


# ─── Scheduling ───
@app.post("/api/schedules")
async def create_schedule(req: ScheduleCreateRequest):
    """스케줄 생성"""
    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT id FROM content_plans WHERE id = ?", (req.plan_id,))
    if not c.fetchone():
        conn.close()
        raise HTTPException(404, "Plan not found")

    c.execute("""
        INSERT INTO schedules (plan_id, scheduled_at)
        VALUES (?, ?)
    """, (req.plan_id, req.scheduled_at))

    # Plan 상태 업데이트
    c.execute("UPDATE content_plans SET status = 'scheduled', updated_at = ? WHERE id = ?",
              (datetime.now().isoformat(), req.plan_id))

    schedule_id = c.lastrowid
    conn.commit()
    conn.close()
    return {"id": schedule_id, "message": "Schedule created"}


@app.get("/api/schedules")
async def get_schedules(status: Optional[str] = None):
    """스케줄 목록"""
    conn = get_db()
    c = conn.cursor()

    if status:
        c.execute("""
            SELECT s.*, cp.title, cp.content_type, cp.reels_style
            FROM schedules s
            LEFT JOIN content_plans cp ON s.plan_id = cp.id
            WHERE s.status = ?
            ORDER BY s.scheduled_at ASC
        """, (status,))
    else:
        c.execute("""
            SELECT s.*, cp.title, cp.content_type, cp.reels_style
            FROM schedules s
            LEFT JOIN content_plans cp ON s.plan_id = cp.id
            ORDER BY s.scheduled_at ASC
        """)

    schedules = [dict(r) for r in c.fetchall()]
    conn.close()
    return {"schedules": schedules}


@app.delete("/api/schedules/{schedule_id}")
async def delete_schedule(schedule_id: int):
    """스케줄 삭제"""
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE schedules SET status = 'cancelled' WHERE id = ?", (schedule_id,))
    conn.commit()
    conn.close()
    return {"message": "Schedule cancelled"}


@app.post("/api/schedules/suggest")
async def suggest_schedule(req: ScheduleSuggestRequest):
    """최적 게시 시간 추천"""
    suggestions = ScheduleManager.suggest_schedule(req.count, req.start_date)
    return {"suggestions": suggestions}


# ─── Tempo Rules ───
@app.get("/api/tempo-rules")
async def get_tempo_rules(content_type: Optional[str] = None):
    conn = get_db()
    c = conn.cursor()
    if content_type:
        c.execute("SELECT * FROM tempo_rules WHERE content_type = ? OR content_type = 'all'", (content_type,))
    else:
        c.execute("SELECT * FROM tempo_rules")
    rules = [dict(r) for r in c.fetchall()]
    conn.close()
    return rules


# ─── Startup ───
@app.on_event("startup")
async def startup():
    init_db()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
