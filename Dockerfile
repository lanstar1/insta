FROM python:3.11-slim

# FFmpeg + 한국어 폰트 설치 (drawtext 필터용)
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg fonts-noto-cjk && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 의존성 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 앱 코드 복사
COPY . .

# 데이터/미디어 디렉토리 생성
RUN mkdir -p /app/data /app/media /app/templates

# Render는 $PORT 환경변수로 포트 지정
ENV PYTHONUNBUFFERED=1
ENV PORT=8000

EXPOSE ${PORT}

# Render 호환: $PORT 사용
CMD uvicorn main:app --host 0.0.0.0 --port $PORT
