FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt prometheus_client

COPY vdm/ vdm/

# Drop to non-root
RUN useradd -r -s /bin/false vdm
USER vdm

EXPOSE 9090
ENTRYPOINT ["python", "-m", "vdm"]
CMD ["--help"]
