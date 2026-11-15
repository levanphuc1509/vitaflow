FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 APP_ENV=production BEHIND_PROXY=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN mkdir -p instance static/uploads && useradd -m app && chown -R app /app
USER app
EXPOSE 8000
# SECRET_KEY, DATABASE_URL... truyền qua biến môi trường khi chạy container
CMD ["gunicorn", "-w", "3", "-k", "gthread", "--threads", "4", "-b", "0.0.0.0:8000", "--access-logfile", "-", "app:app"]
