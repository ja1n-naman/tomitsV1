# tomits web app in a container (core packages only; voice and desktop-notification extras are not needed here).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TOMITS_HOST=0.0.0.0 \
    TOMITS_DB=/data/tomits.db

WORKDIR /app
COPY requirements-core.txt .
RUN pip install --no-cache-dir -r requirements-core.txt

COPY tomits ./tomits
RUN useradd --create-home tomits && mkdir /data && chown tomits /data
USER tomits
VOLUME /data
EXPOSE 3000

CMD ["python", "-m", "tomits.web", "--port", "3000", "--no-browser"]
