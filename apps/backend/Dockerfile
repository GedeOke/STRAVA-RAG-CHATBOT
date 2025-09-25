FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/root/.cache/huggingface \
    TRANSFORMERS_CACHE=/root/.cache/huggingface

WORKDIR /code

COPY requirements.txt /code/requirements.txt

# Install pip dulu
RUN --mount=type=cache,target=/root/.cache/pip \
    python -m pip install --upgrade pip

# Install torch (CPU) langsung dari repo PyTorch
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install torch==2.2.2+cpu --index-url https://download.pytorch.org/whl/cpu

# Baru install requirements lain
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --prefer-binary -r requirements.txt

COPY . /code

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
