"""
YouTube 영상 전사(Transcription) 모듈
수동 자막 입력 → Claude 텍스트 분석 → 핵심 팩트 추출
"""
import os
import re
import json
import logging
from typing import Optional

logger = logging.getLogger("insta-agent.transcriber")

try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

CLAUDE_MODEL = "claude-sonnet-4-20250514"


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

    number_facts = re.findall(r'[가-힣a-zA-Z\s]{2,20}\s*\d+[\d,.]*\s*[가-힣a-zA-Z%원만억천GB TB MB개대배]+', text)
    number_facts = list(set(number_facts[:10]))

    products = re.findall(r'[A-Z][A-Za-z0-9\-]+(?:\s[A-Z0-9][A-Za-z0-9\-]*){0,3}', text)
    products = list(set(products))[:10]

    sentences = re.split(r'[.!?]\s', text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 10]

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
