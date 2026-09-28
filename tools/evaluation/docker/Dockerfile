# Immutable multi-architecture Ubuntu 24.04 image index.
FROM ubuntu:24.04@sha256:008173c23f95b170204355c12626cb5a965d779a7e1283b09e9cffbb1bf33ca3

ENV DEBIAN_FRONTEND=noninteractive \
    PATH=/opt/venv/bin:$PATH \
    XDG_DATA_HOME=/opt/ocr-data \
    PYTHONDONTWRITEBYTECODE=1 \
    OMP_THREAD_LIMIT=1 \
    OPENBLAS_NUM_THREADS=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-venv ca-certificates curl \
    tesseract-ocr=5.3.4-1build5 \
    && rm -rf /var/lib/apt/lists/*
RUN python3 -m venv /opt/venv && python -m pip install --no-cache-dir \
    'setuptools>=77' wheel numpy==2.5.2 opencv-python-headless==4.14.0.94 \
    Pillow==12.3.0 pytest==8.4.2 ruff==0.16.4

WORKDIR /app
COPY . .
RUN python -m pip install --no-cache-dir --no-build-isolation --no-deps --editable . \
    && bash scripts/setup-models.sh \
    && python -m pip freeze > /opt/python-packages.txt \
    && dpkg-query -W > /opt/os-packages.txt

CMD ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider"]
