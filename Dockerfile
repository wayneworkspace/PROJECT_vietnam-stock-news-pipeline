# Container Python riêng cho pipeline Stock (n8n gọi qua HTTP).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 TZ=Asia/Bangkok
WORKDIR /app

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Code được mount từ ./python ở docker-compose, sửa file không cần build lại
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000", "--app-dir", "/app", "--reload"]
