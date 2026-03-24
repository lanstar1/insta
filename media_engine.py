"""
Phase 3: Media Generation Engine
TTS (ElevenLabs) + Image Gen (FLUX/Together) + Video Gen (MiniMax) + FFmpeg Compositing
"""
import os
import json
import time
import subprocess
import tempfile
import shutil
from typing import Optional, List
from pathlib import Path

# ─── API Clients ───
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

# Media output directory
MEDIA_DIR = os.path.join(os.path.dirname(__file__), "media")
os.makedirs(MEDIA_DIR, exist_ok=True)


# ─── 한국어 폰트 감지 (FFmpeg drawtext용) ───
_FONT_PATH_CACHE = None

def _get_cjk_font():
    """한국어 지원 폰트 경로 반환 (캐싱)"""
    global _FONT_PATH_CACHE
    if _FONT_PATH_CACHE is not None:
        return _FONT_PATH_CACHE
    candidates = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJKkr-Regular.otf",
        "/usr/share/fonts/truetype/noto/NotoSansCJKkr-Regular.otf",
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    ]
    for fp in candidates:
        if os.path.exists(fp):
            _FONT_PATH_CACHE = fp
            return fp
    _FONT_PATH_CACHE = ""
    return ""

def _drawtext_font_opt():
    """drawtext 필터용 fontfile 옵션 문자열 반환"""
    fp = _get_cjk_font()
    return f":fontfile='{fp}'" if fp else ""


# ═══════════════════════════════════════════
# TTS Engine (ElevenLabs)
# ═══════════════════════════════════════════

ELEVENLABS_VOICES = {
    "male_friendly": "pNInz6obpgDQGcFmaJgB",   # Adam
    "male_warm": "ErXwobaYiN019PkySvjV",         # Antoni
    "female_pro": "21m00Tcm4TlvDq8ikWAM",        # Rachel
    "male_deep": "VR6AewLTigWG4xSOukaG",         # Arnold
}

DEFAULT_VOICE = "male_friendly"
ELEVENLABS_URL = "https://api.elevenlabs.io/v1/text-to-speech"


def generate_tts(text: str, output_path: str,
                 voice_id: Optional[str] = None,
                 api_key: Optional[str] = None,
                 speed: float = 1.1) -> dict:
    """ElevenLabs TTS로 음성 생성"""

    key = api_key or os.environ.get("ELEVENLABS_API_KEY", "")
    if not key:
        return generate_tts_fallback(text, output_path)

    if not HAS_REQUESTS:
        return {"error": "requests 패키지 필요. pip install requests"}

    vid = voice_id or os.environ.get("ELEVENLABS_VOICE_ID") or ELEVENLABS_VOICES.get(DEFAULT_VOICE, ELEVENLABS_VOICES["male_friendly"])

    try:
        resp = requests.post(
            f"{ELEVENLABS_URL}/{vid}",
            headers={
                "xi-api-key": key,
                "Content-Type": "application/json"
            },
            json={
                "text": text,
                "model_id": "eleven_multilingual_v2",
                "voice_settings": {
                    "stability": 0.5,
                    "similarity_boost": 0.75,
                    "speed": speed
                }
            },
            timeout=30
        )

        if resp.status_code == 200:
            with open(output_path, 'wb') as f:
                f.write(resp.content)
            return {
                "status": "ok",
                "path": output_path,
                "size": len(resp.content),
                "engine": "elevenlabs"
            }
        else:
            return {"error": f"ElevenLabs API 오류: {resp.status_code} {resp.text[:200]}"}

    except Exception as e:
        return {"error": str(e)}


def generate_tts_fallback(text: str, output_path: str) -> dict:
    """API 키 없을 때 로컬 TTS (espeak/pico2wave)"""
    try:
        # pico2wave 시도 (더 자연스러운 음성)
        result = subprocess.run(
            ["which", "pico2wave"], capture_output=True, text=True
        )
        if result.returncode == 0:
            subprocess.run(
                ["pico2wave", "-l", "ko-KR", "-w", output_path, text],
                capture_output=True, timeout=15
            )
            if os.path.exists(output_path):
                return {"status": "ok", "path": output_path, "engine": "pico2wave"}

        # espeak fallback
        result = subprocess.run(
            ["which", "espeak-ng"], capture_output=True, text=True
        )
        if result.returncode == 0:
            subprocess.run(
                ["espeak-ng", "-v", "ko", "-w", output_path, text],
                capture_output=True, timeout=15
            )
            if os.path.exists(output_path):
                return {"status": "ok", "path": output_path, "engine": "espeak-ng"}

        # 빈 WAV 파일 생성 (placeholder)
        return _create_silent_audio(output_path, duration=len(text) / 5.0)

    except Exception as e:
        return {"error": f"Fallback TTS 실패: {e}"}


def _create_silent_audio(output_path: str, duration: float = 3.0) -> dict:
    """FFmpeg로 무음 오디오 생성 (placeholder)"""
    try:
        subprocess.run([
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", f"anullsrc=r=44100:cl=mono",
            "-t", str(duration),
            output_path
        ], capture_output=True, timeout=10)

        if os.path.exists(output_path):
            return {"status": "placeholder", "path": output_path,
                    "engine": "silent", "duration": duration}
    except Exception:
        pass

    return {"error": "무음 오디오 생성 실패"}


# ═══════════════════════════════════════════
# Image Generation (FLUX via Together AI / OpenAI)
# ═══════════════════════════════════════════

def generate_image(prompt: str, output_path: str,
                   provider: str = "together",
                   api_key: Optional[str] = None,
                   width: int = 1080, height: int = 1920) -> dict:
    """이미지 생성 (Together AI FLUX / OpenAI DALL-E)"""

    if provider == "together":
        return _gen_image_together(prompt, output_path, api_key, width, height)
    elif provider == "openai":
        return _gen_image_openai(prompt, output_path, api_key, width, height)
    else:
        return _gen_image_placeholder(prompt, output_path, width, height)


def _gen_image_together(prompt: str, output_path: str,
                        api_key: Optional[str] = None,
                        width: int = 1080, height: int = 1920) -> dict:
    """Together AI (FLUX 1.1 Pro) 이미지 생성"""
    key = api_key or os.environ.get("TOGETHER_API_KEY", "")
    if not key or not HAS_REQUESTS:
        return _gen_image_placeholder(prompt, output_path, width, height)

    try:
        resp = requests.post(
            "https://api.together.xyz/v1/images/generations",
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json"
            },
            json={
                "model": "black-forest-labs/FLUX.1.1-pro",
                "prompt": prompt,
                "width": width,
                "height": height,
                "steps": 28,
                "n": 1,
                "response_format": "b64_json"
            },
            timeout=60
        )

        if resp.status_code == 200:
            import base64
            data = resp.json()
            img_data = base64.b64decode(data["data"][0]["b64_json"])
            with open(output_path, 'wb') as f:
                f.write(img_data)
            return {"status": "ok", "path": output_path, "engine": "flux_1.1_pro"}
        else:
            return {"error": f"Together API: {resp.status_code}"}

    except Exception as e:
        return {"error": str(e)}


def _gen_image_openai(prompt: str, output_path: str,
                      api_key: Optional[str] = None,
                      width: int = 1024, height: int = 1792) -> dict:
    """OpenAI GPT-4o / DALL-E 이미지 생성"""
    key = api_key or os.environ.get("OPENAI_API_KEY", "")
    if not key or not HAS_REQUESTS:
        return _gen_image_placeholder(prompt, output_path, width, height)

    try:
        resp = requests.post(
            "https://api.openai.com/v1/images/generations",
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json"
            },
            json={
                "model": "dall-e-3",
                "prompt": prompt,
                "size": f"{width}x{height}",
                "quality": "hd",
                "n": 1,
                "response_format": "b64_json"
            },
            timeout=60
        )

        if resp.status_code == 200:
            import base64
            data = resp.json()
            img_data = base64.b64decode(data["data"][0]["b64_json"])
            with open(output_path, 'wb') as f:
                f.write(img_data)
            return {"status": "ok", "path": output_path, "engine": "dall-e-3"}
        else:
            return {"error": f"OpenAI API: {resp.status_code}"}

    except Exception as e:
        return {"error": str(e)}


def _gen_image_placeholder(prompt: str, output_path: str,
                           width: int = 1080, height: int = 1920) -> dict:
    """API 없을 때 FFmpeg로 단색+텍스트 placeholder 이미지 생성"""
    try:
        # 텍스트를 짧게
        short = prompt[:60] if len(prompt) > 60 else prompt

        subprocess.run([
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", f"color=c=0x1a1a28:s={width}x{height}:d=1",
            "-vf", f"drawtext=text='{short}':fontsize=36:fontcolor=white:"
                   f"x=(w-text_w)/2:y=(h-text_h)/2{_drawtext_font_opt()}",
            "-frames:v", "1",
            output_path
        ], capture_output=True, timeout=10)

        if os.path.exists(output_path):
            return {"status": "placeholder", "path": output_path, "engine": "ffmpeg"}
    except Exception:
        pass

    return {"error": "Placeholder 이미지 생성 실패"}


# ═══════════════════════════════════════════
# Video Generation (MiniMax Hailuo)
# ═══════════════════════════════════════════

def generate_video(prompt: str, output_path: str,
                   image_path: Optional[str] = None,
                   api_key: Optional[str] = None,
                   duration: int = 5) -> dict:
    """MiniMax/Hailuo 영상 생성"""
    key = api_key or os.environ.get("MINIMAX_API_KEY", "")
    if not key or not HAS_REQUESTS:
        return _gen_video_placeholder(output_path, duration)

    try:
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": "video-01",
            "prompt": prompt,
        }

        if image_path and os.path.exists(image_path):
            import base64
            with open(image_path, 'rb') as f:
                img_b64 = base64.b64encode(f.read()).decode()
            payload["first_frame_image"] = f"data:image/png;base64,{img_b64}"

        # Submit task
        resp = requests.post(
            "https://api.minimaxi.chat/v1/video_generation",
            headers=headers,
            json=payload,
            timeout=30
        )

        if resp.status_code != 200:
            return {"error": f"MiniMax submit: {resp.status_code}"}

        task_id = resp.json().get("task_id")
        if not task_id:
            return {"error": "MiniMax: task_id 없음"}

        # Poll for result (max 3 min)
        for _ in range(36):
            time.sleep(5)
            check = requests.get(
                f"https://api.minimaxi.chat/v1/query/video_generation?task_id={task_id}",
                headers=headers,
                timeout=15
            )
            if check.status_code == 200:
                result = check.json()
                status = result.get("status")
                if status == "Success":
                    video_url = result.get("file_id")
                    if video_url:
                        dl = requests.get(video_url, timeout=60)
                        with open(output_path, 'wb') as f:
                            f.write(dl.content)
                        return {"status": "ok", "path": output_path, "engine": "minimax"}
                elif status == "Fail":
                    return {"error": "MiniMax 생성 실패"}

        return {"error": "MiniMax 타임아웃"}

    except Exception as e:
        return {"error": str(e)}


def _gen_video_placeholder(output_path: str, duration: int = 5) -> dict:
    """API 없을 때 FFmpeg로 간단한 placeholder 영상 생성"""
    try:
        subprocess.run([
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", f"color=c=0x1a1a28:s=1080x1920:d={duration}",
            "-f", "lavfi",
            "-i", f"anullsrc=r=44100:cl=mono",
            "-t", str(duration),
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            output_path
        ], capture_output=True, timeout=30)

        if os.path.exists(output_path):
            return {"status": "placeholder", "path": output_path, "engine": "ffmpeg"}
    except Exception:
        pass
    return {"error": "Placeholder 영상 생성 실패"}


# ═══════════════════════════════════════════
# FFmpeg Compositor
# ═══════════════════════════════════════════

class ReelsCompositor:
    """릴스 영상 합성기"""

    def __init__(self, plan_id: int, output_dir: Optional[str] = None):
        self.plan_id = plan_id
        self.output_dir = output_dir or os.path.join(MEDIA_DIR, f"plan_{plan_id}")
        os.makedirs(self.output_dir, exist_ok=True)
        self.tts_dir = os.path.join(self.output_dir, "tts")
        self.img_dir = os.path.join(self.output_dir, "images")
        self.vid_dir = os.path.join(self.output_dir, "videos")
        os.makedirs(self.tts_dir, exist_ok=True)
        os.makedirs(self.img_dir, exist_ok=True)
        os.makedirs(self.vid_dir, exist_ok=True)

    def generate_scene_assets(self, scenes: list, api_keys: dict = None) -> list:
        """각 씬에 대한 미디어 에셋 생성"""
        keys = api_keys or {}
        results = []

        for i, scene in enumerate(scenes):
            scene_result = {"scene_order": scene.get("scene_order", i+1), "assets": {}}

            # TTS 생성 (나레이션이 있는 경우)
            if scene.get("narration"):
                tts_path = os.path.join(self.tts_dir, f"scene_{i+1}.wav")
                tts_result = generate_tts(
                    scene["narration"], tts_path,
                    api_key=keys.get("elevenlabs")
                )
                scene_result["assets"]["tts"] = tts_result

            # 배경 이미지 생성
            if scene.get("visual_desc"):
                img_path = os.path.join(self.img_dir, f"scene_{i+1}.png")
                img_prompt = self._build_image_prompt(scene)
                img_result = generate_image(
                    img_prompt, img_path,
                    provider=keys.get("image_provider", "placeholder"),
                    api_key=keys.get("together") or keys.get("openai")
                )
                scene_result["assets"]["image"] = img_result

            results.append(scene_result)

        return results

    def _build_image_prompt(self, scene: dict) -> str:
        """씬 정보 → 이미지 프롬프트"""
        base = scene.get("visual_desc", "dark tech background")
        overlay = scene.get("text_overlay", "")
        scene_type = scene.get("scene_type", "normal")

        style = (
            "Modern tech product photography, dark moody background, "
            "cinematic lighting, 9:16 vertical format for Instagram Reels, "
            "clean minimal design, Korean tech content creator style. "
        )

        if scene_type == "hook":
            style += "Bold dramatic composition, high contrast. "
        elif scene_type == "cta":
            style += "Clean call-to-action layout, profile card design. "

        return f"{style}{base}"

    def composite_reels(self, scenes: list, assets: list, output_path: str) -> dict:
        """씬들을 하나의 릴스 영상으로 합성"""
        try:
            # 각 씬을 개별 영상으로 만든 후 concat
            scene_videos = []

            for i, (scene, asset) in enumerate(zip(scenes, assets)):
                scene_vid = os.path.join(self.vid_dir, f"scene_{i+1}.mp4")
                duration = scene.get("duration_sec", 2.0)

                # 배경: 이미지가 있으면 사용, 없으면 단색
                img_path = asset.get("assets", {}).get("image", {}).get("path")
                tts_path = asset.get("assets", {}).get("tts", {}).get("path")

                # 텍스트 오버레이
                text = scene.get("text_overlay", "")
                text_clean = text.replace("'", "").replace('"', '').replace('\n', ' ')

                # FFmpeg 씬 영상 생성
                cmd = ["ffmpeg", "-y"]

                if img_path and os.path.exists(img_path):
                    cmd += ["-loop", "1", "-i", img_path, "-t", str(duration)]
                else:
                    cmd += ["-f", "lavfi", "-i",
                            f"color=c=0x1a1a28:s=1080x1920:d={duration}"]

                if tts_path and os.path.exists(tts_path):
                    cmd += ["-i", tts_path]
                    cmd += ["-shortest"]
                else:
                    cmd += ["-f", "lavfi", "-i",
                            f"anullsrc=r=44100:cl=mono", "-t", str(duration)]

                # Video filter: 텍스트 오버레이
                vf_parts = ["scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:-1:-1"]
                if text_clean:
                    fontsize = 72 if scene.get("scene_type") == "hook" else 48
                    vf_parts.append(
                        f"drawtext=text='{text_clean}':fontsize={fontsize}:"
                        f"fontcolor=white:borderw=3:bordercolor=black:"
                        f"x=(w-text_w)/2:y=(h-text_h)/2{_drawtext_font_opt()}"
                    )

                cmd += [
                    "-vf", ",".join(vf_parts),
                    "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-ar", "44100",
                    "-r", "30",
                    scene_vid
                ]

                subprocess.run(cmd, capture_output=True, timeout=30)
                if os.path.exists(scene_vid):
                    scene_videos.append(scene_vid)

            if not scene_videos:
                return {"error": "씬 영상 생성 실패"}

            # Concat
            concat_file = os.path.join(self.vid_dir, "concat.txt")
            with open(concat_file, 'w') as f:
                for sv in scene_videos:
                    f.write(f"file '{sv}'\n")

            subprocess.run([
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0", "-i", concat_file,
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-c:a", "aac",
                "-movflags", "+faststart",
                output_path
            ], capture_output=True, timeout=60)

            if os.path.exists(output_path):
                # Duration 확인
                probe = subprocess.run([
                    "ffprobe", "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "json", output_path
                ], capture_output=True, text=True, timeout=10)

                dur = 0
                try:
                    dur = float(json.loads(probe.stdout)["format"]["duration"])
                except Exception:
                    pass

                return {
                    "status": "ok",
                    "path": output_path,
                    "duration": round(dur, 1),
                    "scenes": len(scene_videos),
                    "size": os.path.getsize(output_path)
                }

            return {"error": "최종 합성 실패"}

        except Exception as e:
            return {"error": str(e)}


# ═══════════════════════════════════════════
# Card News Composer (Pillow-based)
# ═══════════════════════════════════════════

def compose_card_news(slides: list, output_dir: str,
                      api_keys: dict = None) -> dict:
    """카드뉴스 슬라이드 이미지 생성"""
    keys = api_keys or {}
    os.makedirs(output_dir, exist_ok=True)
    results = []

    for i, slide in enumerate(slides):
        img_path = os.path.join(output_dir, f"slide_{i+1}.png")

        if keys.get("together") or keys.get("openai"):
            prompt = _build_card_prompt(slide, i)
            result = generate_image(
                prompt, img_path,
                provider=keys.get("image_provider", "together"),
                api_key=keys.get("together") or keys.get("openai"),
                width=1080, height=1080  # 카드뉴스는 1:1
            )
        else:
            result = _gen_card_placeholder(slide, img_path, i)

        results.append({"slide": i+1, **result})

    return {"status": "ok", "slides": results, "count": len(results)}


def _build_card_prompt(slide: dict, idx: int) -> str:
    """카드뉴스 슬라이드 → 이미지 프롬프트"""
    text = slide.get("text_overlay", "")
    visual = slide.get("visual_desc", "")
    stype = slide.get("scene_type", "normal")

    style = (
        "Clean minimalist Instagram carousel design, 1:1 square format, "
        "dark background #1a1a28, modern tech aesthetic, "
        "bold Korean typography with product imagery. "
    )

    if stype == "cover":
        style += "Eye-catching cover slide with question hook. "
    elif stype == "cta":
        style += "Call to action slide with save/share prompt. "

    return f"{style}{visual}. Text content: {text}"


def _gen_card_placeholder(slide: dict, output_path: str, idx: int) -> dict:
    """Pillow or FFmpeg로 카드뉴스 placeholder"""
    text = (slide.get("text_overlay") or f"Slide {idx+1}")[:50]
    text_clean = text.replace("'", "").replace('"', '').replace('\n', ' ')

    try:
        subprocess.run([
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", "color=c=0x1a1a28:s=1080x1080:d=1",
            "-vf", f"drawtext=text='{text_clean}':fontsize=48:"
                   f"fontcolor=white:borderw=2:bordercolor=black:"
                   f"x=(w-text_w)/2:y=(h-text_h)/2{_drawtext_font_opt()}",
            "-frames:v", "1",
            output_path
        ], capture_output=True, timeout=10)

        if os.path.exists(output_path):
            return {"status": "placeholder", "path": output_path}
    except Exception:
        pass

    return {"error": "카드뉴스 placeholder 생성 실패"}


# ═══════════════════════════════════════════
# Pipeline Orchestrator
# ═══════════════════════════════════════════

def _resolve_api_keys(api_keys: dict) -> dict:
    """프론트엔드 API 키 + 서버 환경변수 병합. 프론트 입력이 비어있으면 환경변수 사용."""
    keys = dict(api_keys or {})

    # 프론트 입력이 빈 문자열이면 환경변수로 대체
    if not keys.get("elevenlabs"):
        keys["elevenlabs"] = os.environ.get("ELEVENLABS_API_KEY", "")
    if not keys.get("together"):
        keys["together"] = os.environ.get("TOGETHER_API_KEY", "")
    if not keys.get("openai"):
        keys["openai"] = os.environ.get("OPENAI_API_KEY", "")
    if not keys.get("minimax"):
        keys["minimax"] = os.environ.get("MINIMAX_API_KEY", "")

    # image_provider 자동 감지: 프론트에서 placeholder로 왔어도 서버에 키가 있으면 사용
    if keys.get("image_provider") in (None, "", "placeholder"):
        if keys.get("together"):
            keys["image_provider"] = "together"
        elif keys.get("openai"):
            keys["image_provider"] = "openai"
        else:
            keys["image_provider"] = "placeholder"

    return keys


def run_media_pipeline(plan_id: int, content_type: str,
                       scenes: list, api_keys: dict = None) -> dict:
    """전체 미디어 파이프라인 실행"""

    keys = _resolve_api_keys(api_keys)
    output_dir = os.path.join(MEDIA_DIR, f"plan_{plan_id}")
    os.makedirs(output_dir, exist_ok=True)

    if content_type == "reels":
        compositor = ReelsCompositor(plan_id, output_dir)

        # 1. 에셋 생성
        assets = compositor.generate_scene_assets(scenes, keys)

        # 2. 합성
        final_path = os.path.join(output_dir, "final_reels.mp4")
        result = compositor.composite_reels(scenes, assets, final_path)
        result["assets"] = assets
        return result

    elif content_type == "card_news":
        card_dir = os.path.join(output_dir, "cards")
        return compose_card_news(scenes, card_dir, keys)

    elif content_type == "story":
        # 스토리는 단일 이미지 + 선택적 TTS
        story_dir = os.path.join(output_dir, "story")
        os.makedirs(story_dir, exist_ok=True)

        scene = scenes[0] if scenes else {}
        img_path = os.path.join(story_dir, "story_bg.png")
        img_result = generate_image(
            scene.get("visual_desc", "tech background"),
            img_path,
            provider=keys.get("image_provider", "placeholder"),
            api_key=keys.get("together") or keys.get("openai"),
            width=1080, height=1920
        )

        return {"status": "ok", "image": img_result, "type": "story"}

    return {"error": f"Unknown content_type: {content_type}"}
