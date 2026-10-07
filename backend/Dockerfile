FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt requirements-dev.txt ./
# Dev requirements are included so `docker compose run api pytest` works in the same image.
RUN pip install --no-cache-dir -r requirements-dev.txt

COPY . .
RUN chmod +x entrypoint.sh

EXPOSE 8000
CMD ["sh", "entrypoint.sh"]
