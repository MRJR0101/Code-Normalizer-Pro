FROM python:3.11-slim

WORKDIR /app

COPY . .
RUN pip install --no-cache-dir .

ENTRYPOINT ["code-normalizer-pro"]
CMD ["--help"]

