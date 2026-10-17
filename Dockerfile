FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOST=0.0.0.0 PORT=3000 DATA_DIR=/data
WORKDIR /app
COPY server.py create_admin.py retry_feedback.py ./
COPY public ./public
RUN mkdir -p /data && chown 10001:10001 /data && chmod 700 /data
USER 10001:10001
VOLUME ["/data"]
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','3000')+'/api/health',timeout=3)"
CMD ["python", "server.py"]
