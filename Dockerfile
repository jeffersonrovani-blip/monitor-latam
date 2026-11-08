FROM mcr.microsoft.com/playwright/python:v1.58.0-noble
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY monitor.py config.json ./
RUN mkdir -p /app/data && useradd -m -u 10001 monitor && chown -R monitor:monitor /app
USER monitor
CMD ["python", "monitor.py", "status"]
