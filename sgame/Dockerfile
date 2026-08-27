FROM python:3.13-slim

WORKDIR /app

COPY sgame/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY src/sgame ./src/sgame
COPY sgame/frontend ./frontend

ENV PYTHONPATH=/app/src
EXPOSE 8001

CMD ["uvicorn", "sgame.server.app:app", "--host", "0.0.0.0", "--port", "8001"]