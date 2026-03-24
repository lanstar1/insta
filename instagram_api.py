"""
Phase 5: Instagram Graph API Integration
업로드, 스케줄링, 계정 관리
"""
import os
import json
import time
from typing import Optional, List
from datetime import datetime, timedelta

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


# ═══════════════════════════════════════════
# Instagram Graph API Client
# ═══════════════════════════════════════════

class InstagramClient:
    """Instagram Graph API 클라이언트"""

    BASE_URL = "https://graph.facebook.com/v19.0"

    def __init__(self, access_token: str = None, ig_user_id: str = None):
        self.access_token = access_token or os.environ.get("INSTAGRAM_ACCESS_TOKEN", "")
        self.ig_user_id = ig_user_id or os.environ.get("INSTAGRAM_USER_ID", "")

    def _headers(self):
        return {"Authorization": f"Bearer {self.access_token}"}

    def _check_auth(self):
        if not self.access_token or not self.ig_user_id:
            return {"error": "Instagram API 토큰과 사용자 ID가 필요합니다."}
        return None

    # ─── Account Info ───
    def get_account_info(self) -> dict:
        """계정 정보 조회"""
        err = self._check_auth()
        if err:
            return err

        try:
            resp = requests.get(
                f"{self.BASE_URL}/{self.ig_user_id}",
                params={
                    "fields": "id,username,name,profile_picture_url,"
                              "followers_count,follows_count,media_count",
                    "access_token": self.access_token
                },
                timeout=15
            )
            if resp.status_code == 200:
                return {"status": "ok", "account": resp.json()}
            return {"error": f"API 오류: {resp.status_code} {resp.text[:200]}"}
        except Exception as e:
            return {"error": str(e)}

    # ─── Reels Upload ───
    def upload_reels(self, video_url: str, caption: str = "",
                     share_to_feed: bool = True) -> dict:
        """릴스 업로드 (Container → Publish 2단계)"""
        err = self._check_auth()
        if err:
            return err

        try:
            # Step 1: Create container
            resp = requests.post(
                f"{self.BASE_URL}/{self.ig_user_id}/media",
                data={
                    "media_type": "REELS",
                    "video_url": video_url,
                    "caption": caption,
                    "share_to_feed": str(share_to_feed).lower(),
                    "access_token": self.access_token
                },
                timeout=30
            )

            if resp.status_code != 200:
                return {"error": f"Container 생성 실패: {resp.text[:200]}"}

            container_id = resp.json().get("id")
            if not container_id:
                return {"error": "Container ID 없음"}

            # Step 2: Wait for processing
            for _ in range(30):  # max 2.5 min
                time.sleep(5)
                status = self._check_container_status(container_id)
                if status.get("status_code") == "FINISHED":
                    break
                elif status.get("status_code") == "ERROR":
                    return {"error": f"처리 실패: {status.get('status', '')}"}

            # Step 3: Publish
            pub_resp = requests.post(
                f"{self.BASE_URL}/{self.ig_user_id}/media_publish",
                data={
                    "creation_id": container_id,
                    "access_token": self.access_token
                },
                timeout=30
            )

            if pub_resp.status_code == 200:
                media_id = pub_resp.json().get("id")
                return {"status": "ok", "media_id": media_id, "type": "reels"}
            return {"error": f"게시 실패: {pub_resp.text[:200]}"}

        except Exception as e:
            return {"error": str(e)}

    # ─── Carousel (Card News) Upload ───
    def upload_carousel(self, image_urls: List[str], caption: str = "") -> dict:
        """카드뉴스 (캐러셀) 업로드"""
        err = self._check_auth()
        if err:
            return err

        try:
            # Step 1: Create child containers
            children = []
            for url in image_urls:
                resp = requests.post(
                    f"{self.BASE_URL}/{self.ig_user_id}/media",
                    data={
                        "image_url": url,
                        "is_carousel_item": "true",
                        "access_token": self.access_token
                    },
                    timeout=15
                )
                if resp.status_code == 200:
                    children.append(resp.json().get("id"))

            if not children:
                return {"error": "카드 이미지 컨테이너 생성 실패"}

            # Step 2: Create carousel container
            resp = requests.post(
                f"{self.BASE_URL}/{self.ig_user_id}/media",
                data={
                    "media_type": "CAROUSEL",
                    "children": ",".join(children),
                    "caption": caption,
                    "access_token": self.access_token
                },
                timeout=15
            )

            if resp.status_code != 200:
                return {"error": f"캐러셀 컨테이너 실패: {resp.text[:200]}"}

            container_id = resp.json().get("id")

            # Step 3: Publish
            time.sleep(3)
            pub_resp = requests.post(
                f"{self.BASE_URL}/{self.ig_user_id}/media_publish",
                data={
                    "creation_id": container_id,
                    "access_token": self.access_token
                },
                timeout=30
            )

            if pub_resp.status_code == 200:
                return {"status": "ok", "media_id": pub_resp.json().get("id"), "type": "carousel"}
            return {"error": f"게시 실패: {pub_resp.text[:200]}"}

        except Exception as e:
            return {"error": str(e)}

    # ─── Story Upload ───
    def upload_story(self, image_url: str = None, video_url: str = None) -> dict:
        """스토리 업로드"""
        err = self._check_auth()
        if err:
            return err

        try:
            data = {"access_token": self.access_token}
            if video_url:
                data["media_type"] = "STORIES"
                data["video_url"] = video_url
            elif image_url:
                data["media_type"] = "STORIES"
                data["image_url"] = image_url
            else:
                return {"error": "이미지 또는 영상 URL 필요"}

            resp = requests.post(
                f"{self.BASE_URL}/{self.ig_user_id}/media",
                data=data, timeout=30
            )

            if resp.status_code != 200:
                return {"error": f"스토리 컨테이너 실패: {resp.text[:200]}"}

            container_id = resp.json().get("id")
            time.sleep(5)

            pub_resp = requests.post(
                f"{self.BASE_URL}/{self.ig_user_id}/media_publish",
                data={
                    "creation_id": container_id,
                    "access_token": self.access_token
                },
                timeout=30
            )

            if pub_resp.status_code == 200:
                return {"status": "ok", "media_id": pub_resp.json().get("id"), "type": "story"}
            return {"error": f"게시 실패: {pub_resp.text[:200]}"}

        except Exception as e:
            return {"error": str(e)}

    # ─── Helper ───
    def _check_container_status(self, container_id: str) -> dict:
        """컨테이너 처리 상태 확인"""
        try:
            resp = requests.get(
                f"{self.BASE_URL}/{container_id}",
                params={
                    "fields": "status_code,status",
                    "access_token": self.access_token
                },
                timeout=10
            )
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
        return {}

    def get_insights(self, media_id: str) -> dict:
        """미디어 인사이트 조회"""
        try:
            resp = requests.get(
                f"{self.BASE_URL}/{media_id}/insights",
                params={
                    "metric": "impressions,reach,likes,comments,shares,saved,"
                              "plays,total_interactions",
                    "access_token": self.access_token
                },
                timeout=15
            )
            if resp.status_code == 200:
                return {"status": "ok", "insights": resp.json().get("data", [])}
            return {"error": f"인사이트 조회 실패: {resp.status_code}"}
        except Exception as e:
            return {"error": str(e)}


# ═══════════════════════════════════════════
# Scheduling Manager
# ═══════════════════════════════════════════

class ScheduleManager:
    """콘텐츠 스케줄 관리"""

    OPTIMAL_TIMES = {
        "weekday": ["07:00", "12:00", "18:00", "21:00"],
        "weekend": ["09:00", "14:00", "19:00", "21:00"]
    }

    @staticmethod
    def suggest_schedule(count: int, start_date: str = None) -> list:
        """최적 게시 시간 추천"""
        start = datetime.fromisoformat(start_date) if start_date else datetime.now()
        suggestions = []

        current = start
        for i in range(count):
            is_weekend = current.weekday() >= 5
            times = ScheduleManager.OPTIMAL_TIMES["weekend" if is_weekend else "weekday"]

            # 하루에 1~2개씩 배치
            time_idx = i % len(times)
            hour, minute = map(int, times[time_idx].split(":"))
            scheduled = current.replace(hour=hour, minute=minute, second=0)

            if scheduled <= datetime.now():
                scheduled += timedelta(days=1)

            suggestions.append({
                "order": i + 1,
                "datetime": scheduled.isoformat(),
                "day": ['월','화','수','목','금','토','일'][scheduled.weekday()],
                "time": times[time_idx],
                "is_weekend": is_weekend
            })

            # 다음 날로 (2개/일 넘으면)
            if time_idx == len(times) - 1:
                current += timedelta(days=1)

        return suggestions

    @staticmethod
    def get_best_time_for_type(content_type: str) -> str:
        """콘텐츠 유형별 최적 시간"""
        best = {
            "reels": "18:00~21:00",  # 퇴근 후/저녁
            "card_news": "12:00~14:00",  # 점심시간
            "story": "07:00~09:00"  # 아침 출근길
        }
        return best.get(content_type, "18:00~21:00")
