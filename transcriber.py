"""
YouTube 영상 전사(Transcription) 모듈
자막 추출 → 텍스트 분석 → 핵심 팩트 추출
"""
import os
import re
import json
import logging
from typing import Optional

logger = logging.getLogger("insta-agent.transcriber")

try:
    from youtube_transcript_api import YouTubeTranscriptApi
    from youtube_transcript_api.proxies import GenericProxyConfig
    HAS_YT_TRANSCRIPT = True
except ImportError:
    HAS_YT_TRANSCRIPT = False

try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

CLAUDE_MODEL = "claude-sonnet-4-20250514"

# ─── YouTube API 쿠키/프록시 설정 ───
# Render 등 클라우드 환경에서 YouTube IP 차단 우회용
COOKIE_PATH = os.path.join(os.path.dirname(__file__), "data", "cookies.txt")
PROXY_URL = os.environ.get("YT_PROXY_URL", "")  # e.g. http://user:pass@proxy:port


def _build_yt_api():
    """YouTube Transcript API 인스턴스 생성 (쿠키/프록시 적용)"""
    kwargs = {}

    # 프록시 설정
    if PROXY_URL:
        kwargs["proxy_config"] = GenericProxyConfig(
            http_url=PROXY_URL,
            https_url=PROXY_URL,
        )
        logger.info(f"[YT] 프록시 사용: {PROXY_URL[:30]}...")

    # 쿠키 설정 (requests Session에 쿠키 로드)
    if os.path.exists(COOKIE_PATH):
        try:
            import requests
            from http.cookiejar import MozillaCookieJar
            jar = MozillaCookieJar(COOKIE_PATH)
            jar.load(ignore_discard=True, ignore_expires=True)
            session = requests.Session()
            session.cookies = jar
            kwargs["http_client"] = session
            logger.info(f"[YT] 쿠키 로드 완료: {COOKIE_PATH} ({len(jar)}개 쿠키)")
        except Exception as e:
            logger.warning(f"[YT] 쿠키 로드 실패: {e}")

    return YouTubeTranscriptApi(**kwargs)


def extract_video_id(url: str) -> str:
    """유튜브 URL에서 video_id 추출"""
    patterns = [
        r'(?:v=|/v/|youtu\.be/)([a-zA-Z0-9_-]{11})',
        r'(?:embed/)([a-zA-Z0-9_-]{11})',
        r'(?:shorts/)([a-zA-Z0-9_-]{11})',
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return url  # 이미 video_id일 수 있음


def get_transcript(video_url: str) -> dict:
    """
    유튜브 영상 자막 추출
    Returns: {status, transcript, segments, duration_sec, word_count}
    """
    if not HAS_YT_TRANSCRIPT:
        return {"status": "error", "error": "youtube-transcript-api 패키지가 필요합니다."}

    vid = extract_video_id(video_url)
    if not vid:
        return {"status": "error", "error": "유효한 YouTube URL이 아닙니다."}

    try:
        ytt_api = _build_yt_api()

        # 사용 가능한 자막 목록 조회
        transcript_list = ytt_api.list(vid)

        selected = None
        lang_used = ""

        # 1순위: 한국어 수동 자막
        try:
            selected = transcript_list.find_transcript(['ko'])
            lang_used = "ko (수동)" if not selected.is_generated else "ko (자동생성)"
        except Exception:
            pass

        # 2순위: 한국어 자동생성
        if not selected:
            try:
                selected = transcript_list.find_generated_transcript(['ko'])
                lang_used = "ko (자동생성)"
            except Exception:
                pass

        # 3순위: 영어 자막 → 한국어로 번역
        if not selected:
            try:
                en_tr = transcript_list.find_transcript(['en'])
                selected = en_tr.translate('ko')
                lang_used = "en→ko (번역)"
            except Exception:
                pass

        # 4순위: 아무 자막이나
        if not selected:
            try:
                for t in transcript_list:
                    selected = t
                    lang_used = f"{t.language_code} (원본)"
                    break
            except Exception:
                pass

        if not selected:
            return {"status": "error", "error": "자막을 찾을 수 없습니다."}

        segments = selected.fetch()

        # 세그먼트를 dict로 변환
        seg_list = []
        for s in segments:
            seg_list.append({
                "text": s.text if hasattr(s, 'text') else s.get('text', '') if isinstance(s, dict) else str(s),
                "start": s.start if hasattr(s, 'start') else s.get('start', 0) if isinstance(s, dict) else 0,
                "duration": s.duration if hasattr(s, 'duration') else s.get('duration', 0) if isinstance(s, dict) else 0,
            })

        # 전체 텍스트 조합
        full_text = " ".join([s["text"] for s in seg_list])
        full_text = re.sub(r'\s+', ' ', full_text).strip()

        # 타임스탬프 포함 텍스트 (분석용)
        timestamped = []
        for s in seg_list:
            mins = int(s["start"] // 60)
            secs = int(s["start"] % 60)
            timestamped.append(f"[{mins:02d}:{secs:02d}] {s['text']}")

        duration_sec = 0
        if seg_list:
            last = seg_list[-1]
            duration_sec = last["start"] + last["duration"]

        return {
            "status": "ok",
            "video_id": vid,
            "language": lang_used,
            "transcript": full_text,
            "timestamped": "\n".join(timestamped),
            "segments": seg_list,
            "duration_sec": round(duration_sec, 1),
            "word_count": len(full_text),
            "segment_count": len(seg_list),
        }

    except Exception as e:
        logger.error(f"[Transcript] video_id={vid} 전사 실패: {type(e).__name__}: {e}")
        return {"status": "error", "error": f"{type(e).__name__}: {str(e)}"}


def analyze_transcript(transcript_text: str, video_title: str = "",
                       video_topic: str = "", api_key: str = None) -> dict:
    """
    전사 텍스트를 Claude로 분석하여 핵심 팩트와 인스타그램 콘텐츠 아이디어 추출
    """
    key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")

    if not key or not HAS_ANTHROPIC:
        return analyze_transcript_fallback(transcript_text, video_title)

    prompt = f"""너는 IT 유튜버 "LANstar랜스타"의 인스타그램 콘텐츠 기획자야.

아래 유튜브 영상의 전사 텍스트를 분석해서 인스타그램 콘텐츠용 핵심 팩트와 아이디어를 추출해줘.

영상 제목: {video_title}
주제 분류: {video_topic}

## 전사 텍스트:
{transcript_text[:8000]}

## 분석 지시:
아래 JSON 형식으로 응답해. 반드시 유효한 JSON만 출력해.

{{
  "key_facts": [
    "영상에서 언급된 구체적 사실/숫자/스펙 (최소 5개, 최대 10개)"
  ],
  "product_names": ["언급된 제품/서비스/기술명"],
  "pain_points": ["시청자가 공감할 만한 문제점/불편함"],
  "solutions": ["영상에서 제시하는 해결책/팁"],
  "hook_candidates": [
    "릴스 후킹에 쓸 수 있는 임팩트 있는 문장 (결과/숫자 먼저, 3개)"
  ],
  "reels_ideas": [
    {{
      "style": "kinetic_typo 또는 before_after 또는 pov_chat",
      "title": "릴스 제목안",
      "hook": "첫 1.5초 후킹 문구",
      "key_message": "핵심 메시지 1줄"
    }}
  ],
  "card_news_ideas": [
    {{
      "title": "카드뉴스 제목안",
      "slides_outline": ["슬라이드1 요약", "슬라이드2 요약", "..."]
    }}
  ],
  "best_quotes": ["영상에서 가장 인용할 만한 말 (2~3개)"],
  "summary": "영상 전체 내용 3줄 요약"
}}"""

    try:
        client = anthropic.Anthropic(api_key=key)
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=3000,
            messages=[{"role": "user", "content": prompt}]
        )

        text = response.content[0].text.strip()

        # JSON 추출
        json_match = re.search(r'\{[\s\S]*\}', text)
        if json_match:
            result = json.loads(json_match.group())
            result["status"] = "ok"
            result["engine"] = "claude"
            return result

        return {"status": "ok", "engine": "claude", "raw": text}

    except Exception as e:
        logger.error(f"[Analyze] Claude 분석 실패: {type(e).__name__}: {e}")
        return {"status": "error", "error": str(e), "engine": "claude_failed"}


def analyze_transcript_fallback(transcript_text: str, video_title: str = "") -> dict:
    """Claude 없이 기본 텍스트 분석 (키워드/빈도 기반)"""
    text = transcript_text

    # 간단한 키워드 추출 (한국어 조사 제거 후 빈도)
    # 숫자 포함 팩트 추출
    number_facts = re.findall(r'[가-힣a-zA-Z\s]{2,20}\s*\d+[\d,.]*\s*[가-힣a-zA-Z%원만억천GB TB MB개대배]+', text)
    number_facts = list(set(number_facts[:10]))

    # 제품명 패턴 (영문+숫자 조합)
    products = re.findall(r'[A-Z][A-Za-z0-9\-]+(?:\s[A-Z0-9][A-Za-z0-9\-]*){0,3}', text)
    products = list(set(products))[:10]

    # 문장 분리
    sentences = re.split(r'[.!?]\s', text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 10]

    # 후킹 후보 (숫자가 포함된 짧은 문장)
    hooks = [s for s in sentences if re.search(r'\d', s) and len(s) < 60][:5]

    return {
        "status": "ok",
        "engine": "fallback",
        "key_facts": number_facts[:8] if number_facts else ["전사 텍스트에서 자동 추출된 팩트가 없습니다. Claude API를 사용하면 더 정확한 분석이 가능합니다."],
        "product_names": products,
        "pain_points": [],
        "solutions": [],
        "hook_candidates": hooks if hooks else [video_title],
        "reels_ideas": [{
            "style": "kinetic_typo",
            "title": video_title,
            "hook": hooks[0] if hooks else video_title,
            "key_message": sentences[0] if sentences else video_title
        }],
        "card_news_ideas": [],
        "best_quotes": sentences[:3] if sentences else [],
        "summary": " ".join(sentences[:3]) if sentences else video_title,
    }
