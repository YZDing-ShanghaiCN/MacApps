FROM python:3.13-slim

WORKDIR /app

COPY gomoku/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY src/gomoku ./src/gomoku
COPY gomoku/frontend ./frontend

ENV PYTHONPATH=/app/src
EXPOSE 8000

CMD ["uvicorn", "gomoku.server.app:app", "--host", "0.0.0.0", "--port", "8000"]
