FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt prometheus_client

COPY avd_masters/ avd_masters/

# Drop to non-root
RUN useradd -r -s /bin/false avdmasters
USER avdmasters

EXPOSE 9090
ENTRYPOINT ["python", "-m", "avd_masters"]
CMD ["--help"]
