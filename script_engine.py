"""
Phase 2: Script Generation Engine
Claude API를 사용한 릴스/카드뉴스/스토리 스크립트 자동 생성
"""
import os
import json
import re
from typing import Optional

# Claude API (anthropic SDK)
try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

CLAUDE_MODEL = "claude-sonnet-4-20250514"

# ─── 프롬프트 템플릿 ───

PERSONA = """너는 IT 유튜버 "LANstar랜스타"의 인스타그램 콘텐츠 작가야.
말투: IT 잘 아는 친한 형이 알려주는 느낌. 반말+존댓말 믹스. ㅋㅋ 자연스럽게 사용.
금지어: "~하겠습니다", "~드리겠습니다", "안녕하세요 여러분", "본 콘텐츠에서는", "오늘 소개해드릴"
스타일: 짧고 임팩트 있게. 어려운 IT 용어는 쉬운 비유로."""

REELS_KINETIC = """## 릴스 - 키네틱 타이포 스타일
구조: 결과를 먼저 보여주고(Hook), 방법을 나중에 풀기.
- 씬1 (Hook, 1.5~3초): 결과/숫자 임팩트. 큰 텍스트가 팍 등장.
- 씬2~4 (본문, 각 1~2초): 제품/방법 소개. 컷 빠르게 전환.
- 씬5 (CTA, 3~5초): 프로필 링크/팔로우 유도. 가볍게.
전체 길이: 20~35초. TTS 분당 280~320자.
음소거 시청자 고려: 텍스트만으로 정보 전달 100%."""

REELS_BEFORE_AFTER = """## 릴스 - Before/After 스타일
구조: 상하 분할 화면으로 문제 vs 해결 동시 표시.
- 씬1 (Hook, 2초): 분할 화면 + 숫자 대비 (예: 50 vs 900)
- 씬2 (방법, 3~5초): 어떻게 해결하는지 간단히.
- 씬3 (활용, 3~5초): 어떤 상황에서 유용한지.
- 씬4 (CTA, 3초): 프로필 링크.
비교 대상이 명확한 주제에 최적."""

REELS_POV = """## 릴스 - POV 상황극 (카톡 대화) 스타일
구조: 카카오톡 대화 형식으로 일상 공감 상황 연출.
- 씬1 (설정, 2초): "POV: [상황]" 헤더 + 공감 이모지.
- 씬2~3 (대화, 각 3~4초): 친구와 카톡 대화. 문제 제기 → 해결책 소개.
- 씬4 (증거, 3초): 속도/성능 캡쳐 인증.
- 씬5 (CTA, 2초): "프로필 링크" 유도.
유머와 공감이 핵심. DM 공유 극대화."""

REELS_CARTOON = """## 릴스 - 카툰 스타일
구조: 캐릭터 + 말풍선 + 만화 이펙트.
- 씬1 (Hook, 2초): 캐릭터가 짜증/당황하는 상황.
- 씬2 (아이디어, 2초): 💡 캐릭터가 해결책 발견.
- 씬3 (실행, 3초): 제품 사용 장면. 만화 효과음.
- 씬4 (결과, 3초): 임팩트 숫자 + 놀란 표정.
- 씬5 (CTA, 2초): 프로필 카드."""

CARD_NEWS_TEMPLATE = """## 카드뉴스 스크립트
구조: 이미지 중심, 텍스트 최소화. 슬라이드 5~8장.
- 1장 (커버): 질문형 타이틀 + 제품 이미지. "뭘 사야 하지?" 스타일.
- 2~4장 (정보): 각 항목당 한줄 카피 + 핵심 수치 1개. 비교표 활용.
- 5장 (비교): 한눈에 보는 비교 (이모지 + 짧은 텍스트).
- 마지막장 (CTA): "저장해두고 살 때 꺼내봐!" + 유튜브 유도.
캡션에는 해시태그 5~8개."""

STORY_TEMPLATE = """## 스토리 스크립트
유형: quiz(퀴즈), poll(투표), alert(영상알림) 중 택1.
- quiz: 의외의 정답이 있는 3~4지선다. 공유 유발.
- poll: 두 가지 선택지 대결. 참여 유발.
- alert: 새 영상 티저. 궁금증 유발 + 스와이프업 CTA.
텍스트 극도로 최소화. 실사 이미지 배경."""


STYLE_TEMPLATES = {
    "kinetic_typo": REELS_KINETIC,
    "before_after": REELS_BEFORE_AFTER,
    "pov_chat": REELS_POV,
    "cartoon": REELS_CARTOON,
}


def build_prompt(video_title: str, video_topic: str, video_summary: str,
                 content_type: str, reels_style: Optional[str] = None,
                 hook_text: Optional[str] = None, target_duration: int = 25,
                 transcript: str = "", transcript_analysis: str = "") -> str:
    """콘텐츠 유형에 맞는 스크립트 생성 프롬프트 구성"""

    if content_type == "reels":
        style_guide = STYLE_TEMPLATES.get(reels_style, REELS_KINETIC)
        output_format = """
출력 형식 (JSON):
{
  "title": "릴스 제목 (캡션용, 30자 이내)",
  "hook_text": "첫 1.5초에 보여줄 후킹 텍스트",
  "caption": "인스타 캡션 (해시태그 포함)",
  "scenes": [
    {
      "scene_order": 1,
      "scene_type": "hook",
      "duration_sec": 2.0,
      "text_overlay": "화면에 표시될 큰 텍스트",
      "narration": "TTS로 읽을 나레이션 (없으면 null)",
      "visual_desc": "배경 영상/이미지 설명"
    }
  ]
}"""
    elif content_type == "card_news":
        style_guide = CARD_NEWS_TEMPLATE
        output_format = """
출력 형식 (JSON):
{
  "title": "카드뉴스 제목",
  "caption": "인스타 캡션 (해시태그 포함)",
  "slides": [
    {
      "scene_order": 1,
      "scene_type": "cover",
      "text_overlay": "슬라이드 메인 텍스트 (짧게!)",
      "sub_text": "서브 텍스트 (있으면)",
      "visual_desc": "배경/이미지 설명",
      "narration": null
    }
  ]
}"""
    else:  # story
        style_guide = STORY_TEMPLATE
        output_format = """
출력 형식 (JSON):
{
  "title": "스토리 제목",
  "story_type": "quiz 또는 poll 또는 alert",
  "background_desc": "배경 이미지 설명",
  "main_text": "메인 텍스트 (짧게!)",
  "options": ["선택지1", "선택지2", ...],
  "correct_answer": "정답 (quiz인 경우)",
  "cta_text": "스와이프업 CTA 텍스트",
  "caption": null
}"""

    # 전사 섹션 구성 (f-string 중첩 회피)
    transcript_section = ""
    if transcript:
        t_text = transcript[:6000]
        transcript_section = f"\n## 영상 전사 텍스트 (팩트 기반 콘텐츠 소스):\n{t_text}\n"
    analysis_section = ""
    if transcript_analysis:
        analysis_section = f"\n## 전사 분석 결과:\n{transcript_analysis}\n"

    fact_instruction = ""
    if transcript or transcript_analysis:
        fact_instruction = "\n**중요: 전사 텍스트에 있는 구체적 사실, 숫자, 제품명, 비교 데이터를 반드시 활용해.**"

    hook_line = f"- 후킹 텍스트 힌트: {hook_text}" if hook_text else ""
    dur_line = f"- 목표 길이: {target_duration}초" if content_type == "reels" else ""

    prompt = f"""{PERSONA}

{style_guide}

## 원본 영상 정보
- 제목: {video_title}
- 주제: {video_topic}
- 요약: {video_summary}
{hook_line}
{dur_line}
{transcript_section}{analysis_section}
위 영상의 핵심 내용을 기반으로 인스타그램 {content_type} 스크립트를 생성해줘.{fact_instruction}
AI가 만든 느낌이 아닌, 자연스럽고 유머러스하고 정보성 있는 톤으로.
공유/저장을 유발할 수 있는 임팩트 있는 내용으로 만들어줘.

{output_format}

JSON만 출력해. 다른 설명 없이."""

    return prompt


def generate_script_claude(video_title: str, video_topic: str, video_summary: str,
                           content_type: str, reels_style: Optional[str] = None,
                           hook_text: Optional[str] = None, target_duration: int = 25,
                           api_key: Optional[str] = None,
                           transcript: str = "", transcript_analysis: str = "") -> dict:
    """Claude API로 스크립트 생성 (전사 텍스트가 있으면 팩트 기반)"""

    key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        return generate_script_fallback(video_title, video_topic, video_summary,
                                         content_type, reels_style, hook_text, target_duration)

    if not HAS_ANTHROPIC:
        return {"error": "anthropic 패키지가 설치되어 있지 않습니다. pip install anthropic"}

    client = anthropic.Anthropic(api_key=key)
    prompt = build_prompt(video_title, video_topic, video_summary,
                          content_type, reels_style, hook_text, target_duration,
                          transcript=transcript, transcript_analysis=transcript_analysis)

    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}]
        )
        text = response.content[0].text.strip()

        # JSON 추출
        json_match = re.search(r'\{[\s\S]*\}', text)
        if json_match:
            return json.loads(json_match.group())
        return {"error": "JSON 파싱 실패", "raw": text}

    except Exception as e:
        return {"error": str(e)}


def generate_script_fallback(video_title: str, video_topic: str, video_summary: str,
                              content_type: str, reels_style: Optional[str] = None,
                              hook_text: Optional[str] = None, target_duration: int = 25) -> dict:
    """Claude API 없을 때 로컬 템플릿 기반 스크립트 생성"""

    clean_title = re.sub(r'\[.*?\]', '', video_title).strip()
    clean_title = re.sub(r'\(.*?\)', '', clean_title).strip()
    short_title = clean_title[:20] if len(clean_title) > 20 else clean_title

    if content_type == "reels":
        hook = hook_text or f"{short_title}?"
        if reels_style == "before_after":
            return {
                "title": clean_title,
                "hook_text": hook,
                "caption": f"{clean_title} 비교해봄 ㅋㅋ #{video_topic.replace('/','')} #IT꿀팁 #랜스타 #비포애프터",
                "scenes": [
                    {"scene_order": 1, "scene_type": "hook", "duration_sec": 2.0,
                     "text_overlay": hook, "narration": None,
                     "visual_desc": "분할 화면 - Before/After 비교"},
                    {"scene_order": 2, "scene_type": "normal", "duration_sec": 2.0,
                     "text_overlay": "이렇게 하면 됨", "narration": f"{clean_title} 방법 알려줄게",
                     "visual_desc": "제품/방법 소개"},
                    {"scene_order": 3, "scene_type": "normal", "duration_sec": 2.0,
                     "text_overlay": "이런 상황에서 유용", "narration": None,
                     "visual_desc": "활용 장면"},
                    {"scene_order": 4, "scene_type": "cta", "duration_sec": 3.0,
                     "text_overlay": "자세한 건 프로필 링크!", "narration": None,
                     "visual_desc": "프로필 카드"}
                ]
            }
        elif reels_style == "pov_chat":
            return {
                "title": clean_title,
                "hook_text": hook,
                "caption": f"친구한테 알려줬더니 바로 링크 달라고 함 ㅋㅋ #{video_topic.replace('/','')} #IT꿀팁 #POV",
                "scenes": [
                    {"scene_order": 1, "scene_type": "hook", "duration_sec": 2.0,
                     "text_overlay": f"POV: {short_title} 해결한 나", "narration": None,
                     "visual_desc": "POV 헤더 + 이모지"},
                    {"scene_order": 2, "scene_type": "normal", "duration_sec": 3.0,
                     "text_overlay": None, "narration": "야 이거 어떻게 해결했어?",
                     "visual_desc": "카톡 대화 - 친구 질문"},
                    {"scene_order": 3, "scene_type": "normal", "duration_sec": 3.0,
                     "text_overlay": None, "narration": f"{clean_title} 하나면 됨",
                     "visual_desc": "카톡 대화 - 내 답변"},
                    {"scene_order": 4, "scene_type": "result", "duration_sec": 2.5,
                     "text_overlay": "링크 보내줘!!", "narration": None,
                     "visual_desc": "친구 반응 + 인증"},
                    {"scene_order": 5, "scene_type": "cta", "duration_sec": 2.0,
                     "text_overlay": "프로필 링크 ㄱㄱ", "narration": None,
                     "visual_desc": "CTA"}
                ]
            }
        else:  # kinetic_typo (default)
            return {
                "title": clean_title,
                "hook_text": hook,
                "caption": f"{clean_title} 꿀팁 🔥 #{video_topic.replace('/','')} #IT꿀팁 #랜스타",
                "scenes": [
                    {"scene_order": 1, "scene_type": "hook", "duration_sec": 2.0,
                     "text_overlay": hook, "narration": None,
                     "visual_desc": "큰 텍스트 팝 등장 + 제품 배경"},
                    {"scene_order": 2, "scene_type": "normal", "duration_sec": 2.0,
                     "text_overlay": "이거 하나면 됨", "narration": f"{clean_title} 방법",
                     "visual_desc": "제품 클로즈업"},
                    {"scene_order": 3, "scene_type": "normal", "duration_sec": 1.5,
                     "text_overlay": "꽂기만 하면 끝!", "narration": "진짜 간단함",
                     "visual_desc": "사용 장면"},
                    {"scene_order": 4, "scene_type": "result", "duration_sec": 2.0,
                     "text_overlay": "체감 실화?", "narration": None,
                     "visual_desc": "결과/수치 비교"},
                    {"scene_order": 5, "scene_type": "cta", "duration_sec": 3.0,
                     "text_overlay": "프로필 링크에서 확인!", "narration": None,
                     "visual_desc": "프로필 카드 + 팔로우 버튼"}
                ]
            }

    elif content_type == "card_news":
        return {
            "title": clean_title,
            "caption": f"{clean_title} 저장 필수 📌 #{video_topic.replace('/','')} #IT꿀팁 #랜스타",
            "slides": [
                {"scene_order": 1, "scene_type": "cover",
                 "text_overlay": f"{short_title}\n뭘 골라야 하지?",
                 "sub_text": None, "visual_desc": "제품 이미지 컷아웃 + 배경", "narration": None},
                {"scene_order": 2, "scene_type": "normal",
                 "text_overlay": "첫 번째 선택지",
                 "sub_text": "핵심 한줄 요약", "visual_desc": "제품A 비주얼", "narration": None},
                {"scene_order": 3, "scene_type": "normal",
                 "text_overlay": "두 번째 선택지",
                 "sub_text": "핵심 한줄 요약", "visual_desc": "제품B 비주얼", "narration": None},
                {"scene_order": 4, "scene_type": "normal",
                 "text_overlay": "한눈에 비교",
                 "sub_text": None, "visual_desc": "비교표", "narration": None},
                {"scene_order": 5, "scene_type": "cta",
                 "text_overlay": "저장해두고\n살 때 꺼내봐!",
                 "sub_text": "유튜브 LANstar랜스타", "visual_desc": "CTA 배경", "narration": None}
            ]
        }

    else:  # story
        return {
            "title": clean_title,
            "story_type": "quiz",
            "background_desc": f"{video_topic} 관련 제품 이미지",
            "main_text": f"{short_title},\n뭐에 쓰는 물건?",
            "options": ["장식용 ㅋ", "정답 항목", "충전용", "프린터 연결"],
            "correct_answer": "정답 항목",
            "cta_text": "자세한 영상 보기",
            "caption": None
        }


def check_spelling(text: str) -> list:
    """간단한 맞춤법 체크 (기본 패턴 기반)"""
    issues = []
    patterns = [
        (r'되요', '돼요', '되요 → 돼요'),
        (r'됬', '됐', '됬 → 됐'),
        (r'안됀', '안 된', '안됀 → 안 된'),
        (r'몇일', '며칠', '몇일 → 며칠'),
        (r'왠지', '웬지', '왠지(왜인지) vs 웬지(웬일인지) 확인'),
        (r'걸리므로써', '걸림으로써', '~므로써 → ~ㅁ으로써'),
        (r'금새', '금세', '금새 → 금세'),
        (r'어의없', '어이없', '어의없 → 어이없'),
    ]
    for pattern, fix, desc in patterns:
        if re.search(pattern, text):
            issues.append({"pattern": pattern, "suggestion": fix, "description": desc})
    return issues
