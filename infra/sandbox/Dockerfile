# Validation sandbox image for eval-optimizer (C4/C5).
# Runs candidate code's syntax/ruff/pytest checks in isolation (--network none).
# Build once:  docker build -t evalopt-sandbox infra/sandbox
FROM python:3.13-slim
RUN pip install --no-cache-dir ruff pytest
WORKDIR /w
