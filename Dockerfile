# site/ 와 private/guide.pdf 는 먼저 build.py 로 만들어 함께 넣는다.
FROM python:3.13-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg fonts-nanum && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY server.py product.py more.py extra.py oauth.py db.py asr_worker.py ./
COPY site site
COPY private private
ENV HOST=0.0.0.0 PORT=8800 DATA_DIR=/data COOKIE_SECURE=1 ASR_PYTHON=/usr/local/bin/python OLLAMA_URL=http://ollama:11434 HF_HOME=/data/hf
VOLUME /data
EXPOSE 8800
CMD ["python", "server.py"]
