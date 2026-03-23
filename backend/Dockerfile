FROM python:3.11-slim

WORKDIR /app

# 시스템 의존성
RUN apt-get update && apt-get install -y --no-install-recommends \
    libxml2-dev libxslt1-dev gcc \
    && rm -rf /var/lib/apt/lists/*

# Python 의존성
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

# 프로젝트 전체 복사 (agent, utils, skills 등 필요)
COPY agent/ /app/agent/
COPY utils/ /app/utils/
COPY skills/ /app/skills/
COPY agent_skills/ /app/agent_skills/
COPY ir_schema.py /app/ir_schema.py
COPY backend/ /app/backend/

# 작업 디렉토리
RUN mkdir -p /app/uploads /app/outputs

ENV PYTHONPATH=/app:/app/backend
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
