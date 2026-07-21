# HarmonAI — Streamlit uygulaması için container image
#
# Notlar:
#  - basic-pitch (TensorFlow) + librosa nedeniyle image büyük olacak (~2-3GB), normaldir.
#  - chromium/chromium-driver yalnızca web_scraper.py'nin Selenium fallback'i için
#    (requests başarısız olursa devreye girer). Web scraping'e ihtiyacın yoksa bu
#    iki paketi kaldırıp image'ı belirgin küçültebilirsin.
#  - ffmpeg, yt-dlp'nin ses dönüşümü için zorunlu.

FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsndfile1 \
    build-essential \
    chromium \
    chromium-driver \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD curl --fail http://localhost:8501/_stcore/health || exit 1

ENTRYPOINT ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
