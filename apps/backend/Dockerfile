# syntax=docker/dockerfile:1.7
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
    # HAPUS PIP_NO_CACHE_DIR=1!

# (opsional, biar cache model HF tersimpan di satu tempat dan bisa di-mount)
ENV HF_HOME=/root/.cache/huggingface \
    TRANSFORMERS_CACHE=/root/.cache/huggingface

WORKDIR /code

# 1) Copy requirements dulu, biar layer install ke-cache
COPY requirements.txt /code/requirements.txt

# 2) Install deps dgn cache pip (BuildKit)
#    - upgrade pip sekali
#    - prefer binary wheels biar cepat (torch, dll)
RUN --mount=type=cache,target=/root/.cache/pip \
    python -m pip install --upgrade pip && \
    pip install --prefer-binary -r requirements.txt

# 3) Baru copy source code
COPY . /code

# 4) Jalankan app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
