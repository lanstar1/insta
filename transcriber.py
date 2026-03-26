"""
YouTube 영상 전사(Transcription) 모듈
자막 추출 → 텍스트 분석 → 핵심 팩트 추출

yt-dlp (1차) → youtube-transcript-api (폴백) 이중 구조
yt-dlp는 클라우드 IP 차단을 우회할 수 있음
"""
import os
import re
import json
import logging
from typing import Optional

logger = logging.getLogger("insta-agent.transcriber")

# ─── yt-dlp (1차 엔진) ───
try:
    import yt_dlp
    HAS_YTDLP = True
except Exception as _e:
    HAS_YTDLP = False
    print(f"[Transcriber] yt-dlp import 실패: {_e}")

# ─── youtube-transcript-api (폴백 엔진) ───
try:
    from youtube_transcript_api import YouTubeTranscriptApi
    HAS_YT_TRANSCRIPT = True
except ImportError:
    HAS_YT_TRANSCRIPT = False

try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

# 시작 시 엔진 상태 로그
print(f"[Transcriber] 엔진 상태: yt-dlp={HAS_YTDLP}, yt-transcript-api={HAS_YT_TRANSCRIPT}, anthropic={HAS_ANTHROPIC}")

CLAUDE_MODEL = "claude-sonnet-4-20250514"

# 쿠키 파일 경로 (yt-dlp에서 사용)
COOKIE_PATH = os.path.join(os.path.dirname(__file__), "data", "cookies.txt")


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


def _get_transcript_ytdlp(vid: str) -> dict:
    """yt-dlp를 사용한 자막 추출 (클라우드 IP 차단 우회 가능)"""
    video_url = f"https://www.youtube.com/watch?v={vid}"

    ydl_opts = {
        'skip_download': True,
        'writeautomaticsub': True,
        'writesubtitles': True,
        'subtitleslangs': ['ko', 'en'],
        'subtitlesformat': 'json3',
        'quiet': True,
        'no_warnings': True,
    }

    # 쿠키 파일이 있으면 사용
    if os.path.exists(COOKIE_PATH):
        ydl_opts['cookiefile'] = COOKIE_PATH
        logger.warning(f"[yt-dlp] 쿠키 파일 사용: {COOKIE_PATH}")

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(video_url, download=False)

    subs = info.get('subtitles', {})
    auto_subs = info.get('automatic_captions', {})

    # 자막 선택 우선순위: ko 수동 → ko 자동 → en 수동 → en 자동
    sub_data = None
    lang_used = ""

    for lang, label, source in [
        ('ko', 'ko (수동)', subs),
        ('ko', 'ko (자동생성)', auto_subs),
        ('en', 'en (수동)', subs),
        ('en', 'en (자동생성)', auto_subs),
    ]:
        if lang in source:
            # json3 포맷 URL 찾기
            for fmt in source[lang]:
                if fmt.get('ext') == 'json3':
                    sub_data = fmt
                    lang_used = label
                    break
            if sub_data:
                break

    if not sub_data:
        return {"status": "error", "error": "자막을 찾을 수 없습니다 (yt-dlp)."}

    # json3 자막 데이터 다운로드 및 파싱
    import requests
    resp = requests.get(sub_data['url'], timeout=15)
    resp.raise_for_status()
    caption_data = resp.json()

    events = caption_data.get('events', [])
    seg_list = []
    for ev in events:
        if 'segs' in ev:
            text = ''.join(s.get('utf8', '') for s in ev['segs']).strip()
            if text and text != '\n':
                start = ev.get('tStartMs', 0) / 1000
                dur = ev.get('dDurationMs', 0) / 1000
                seg_list.append({'text': text, 'start': start, 'duration': dur})

    if not seg_list:
        return {"status": "error", "error": "자막 세그먼트가 비어있습니다."}

    # 전체 텍스트 조합
    full_text = " ".join([s["text"] for s in seg_list])
    full_text = re.sub(r'\s+', ' ', full_text).strip()

    # 타임스탬프 포함 텍스트
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
        "engine": "yt-dlp",
    }


def _get_transcript_api(vid: str) -> dict:
    """youtube-transcript-api를 사용한 자막 추출 (폴백)"""
    ytt_api = YouTubeTranscriptApi()
    transcript_list = ytt_api.list(vid)

    selected = None
    lang_used = ""

    # 1순위: 한국어 자막
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

    # 3순위: 영어 → 한국어 번역
    if not selected:
        try:
            en_tr = transcript_list.find_transcript(['en'])
            selected = en_tr.translate('ko')
            lang_used = "en→ko (번역)"
        except Exception:
            pass

    # 4순위: 아무 자막
    if not selected:
        try:
            for t in transcript_list:
                selected = t
                lang_used = f"{t.language_code} (원본)"
                break
        except Exception:
            pass

    if not selected:
        return {"status": "error", "error": "자막을 찾을 수 없습니다 (API)."}

    segments = selected.fetch()
    seg_list = []
    for s in segments:
        seg_list.append({
            "text": s.text if hasattr(s, 'text') else s.get('text', '') if isinstance(s, dict) else str(s),
            "start": s.start if hasattr(s, 'start') else s.get('start', 0) if isinstance(s, dict) else 0,
            "duration": s.duration if hasattr(s, 'duration') else s.get('duration', 0) if isinstance(s, dict) else 0,
        })

    full_text = " ".join([s["text"] for s in seg_list])
    full_text = re.sub(r'\s+', ' ', full_text).strip()

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
        "engine": "yt-transcript-api",
    }


def get_transcript(video_url: str) -> dict:
    """
    유튜브 영상 자막 추출
    1차: yt-dlp (클라우드 IP 차단 우회)
    2차: youtube-transcript-api (폴백)
    """
    vid = extract_video_id(video_url)
    if not vid:
        return {"status": "error", "error": "유효한 YouTube URL이 아닙니다."}

    # 1차: yt-dlp 시도
    if HAS_YTDLP:
        try:
            logger.warning(f"[Transcript] yt-dlp로 시도: {vid}")
            result = _get_transcript_ytdlp(vid)
            if result.get("status") == "ok":
                logger.warning(f"[Transcript] yt-dlp 성공: {vid} ({result.get('word_count', 0)}자)")
                return result
            logger.warning(f"[Transcript] yt-dlp 실패: {result.get('error', '?')}")
        except Exception as e:
            logger.warning(f"[Transcript] yt-dlp 예외: {type(e).__name__}: {e}")

    # 2차: youtube-transcript-api 폴백
    if HAS_YT_TRANSCRIPT:
        try:
            logger.warning(f"[Transcript] youtube-transcript-api로 폴백: {vid}")
            result = _get_transcript_api(vid)
            if result.get("status") == "ok":
                logger.warning(f"[Transcript] API 폴백 성공: {vid}")
                return result
            logger.warning(f"[Transcript] API 폴백 실패: {result.get('error', '?')}")
            return result
        except Exception as e:
            logger.error(f"[Transcript] API 폴백 예외: {type(e).__name__}: {e}")
            return {"status": "error", "error": f"{type(e).__name__}: {str(e)}"}

    return {"status": "error", "error": "자막 추출 패키지가 없습니다 (yt-dlp 또는 youtube-transcript-api 필요)."}


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
