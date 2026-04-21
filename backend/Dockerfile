# Stage 1: Builder Stage - Install dependencies including build tools and CUDA toolkit components
FROM nvidia/cuda:12.1.1-cudnn8-devel-ubuntu22.04 AS builder

# Avoid prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive

# Install Python 3.10, pip, build essentials, git, and other system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.10 \
    python3-pip \
    python3.10-dev \
    python3.10-venv \
    build-essential \
    git \
    libsndfile1 \
    libportaudio2 \
    ffmpeg \
    portaudio19-dev \
    python3-setuptools \
    python3.10-distutils \
    ninja-build \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Make python3.10 the default python/pip
RUN update-alternatives --install /usr/bin/python python /usr/bin/python3.10 1 && \
    update-alternatives --install /usr/bin/pip pip /usr/bin/pip3 1

# Set working directory
WORKDIR /app

# Upgrade pip
RUN pip install --no-cache-dir --upgrade pip

# Install PyTorch with CUDA 12.1 support
RUN pip install --no-cache-dir \
    torch==2.5.1+cu121 \
    torchaudio==2.5.1+cu121 \
    torchvision==0.20.1 \
    --index-url https://download.pytorch.org/whl/cu121

# Install DeepSpeed
ENV DS_BUILD_TRANSFORMER=1
ENV DS_BUILD_CPU_ADAM=0
ENV DS_BUILD_FUSED_ADAM=0
ENV DS_BUILD_UTILS=0
ENV DS_BUILD_OPS=0

RUN echo "Building DeepSpeed with flags: DS_BUILD_TRANSFORMER=${DS_BUILD_TRANSFORMER}, DS_BUILD_CPU_ADAM=${DS_BUILD_CPU_ADAM}, DS_BUILD_FUSED_ADAM=${DS_BUILD_FUSED_ADAM}, DS_BUILD_UTILS=${DS_BUILD_UTILS}, DS_BUILD_OPS=${DS_BUILD_OPS}" && \
    pip install --no-cache-dir deepspeed \
    || (echo "DeepSpeed install failed. Check build logs above." && exit 1)

# Copy requirements file first to leverage Docker cache
COPY --chown=1001:1001 requirements.txt .

# Install remaining Python dependencies from requirements.txt
RUN pip install --no-cache-dir --prefer-binary -r requirements.txt \
    || (echo "pip install -r requirements.txt FAILED." && exit 1)

# Pin ctranslate2 to a compatible version
RUN pip install --no-cache-dir "ctranslate2<4.5.0"

RUN pip install --no-cache-dir transformers==4.36.2

# --- Stage 2: Runtime Stage ---
# Base image still needs CUDA toolkit for PyTorch/DeepSpeed/etc in the app
FROM nvidia/cuda:12.1.1-cudnn8-devel-ubuntu22.04

# Avoid prompts
ENV DEBIAN_FRONTEND=noninteractive

# Install runtime dependencies for the APP + gosu
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.10 \
    python3-pip \
    python3.10-dev \
    libsndfile1 \
    ffmpeg \
    libportaudio2 \
    python3-setuptools \
    python3.10-distutils \
    ninja-build \
    build-essential \
    g++ \
    curl \
    gosu \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Make python3.10 the default python
RUN update-alternatives --install /usr/bin/python python /usr/bin/python3.10 1 && \
    update-alternatives --install /usr/bin/pip pip /usr/bin/pip3 1

# Create a non-root user and group before seeding runtime caches
RUN groupadd --gid 1001 appgroup && \
    useradd --uid 1001 --gid 1001 --create-home appuser

# Keep cache paths aligned with the runtime user and mounted volumes
ENV HOME=/home/appuser
ENV HF_HOME=${HOME}/.cache/huggingface
ENV TORCH_HOME=${HOME}/.cache/torch

# Prepare runtime directories before copying dependencies and preloading models
WORKDIR /app
RUN mkdir -p /usr/local/lib/python3.10/dist-packages \
    /app/code \
    "${HF_HOME}" \
    "${TORCH_HOME}"

# Copy installed Python packages from the builder stage
COPY --chown=1001:1001 --from=builder /usr/local/lib/python3.10/dist-packages /usr/local/lib/python3.10/dist-packages

# <<<--- Keep other model pre-downloads --->>>
# <<<--- Silero VAD Pre-download --->>>
RUN echo "Preloading Silero VAD model..." && \
    python3 <<EOF
import torch
import os
try:
    # Keep build-time downloads in the same cache path used at runtime
    cache_dir = os.environ.get("TORCH_HOME", os.path.expanduser("~/.cache/torch"))
    os.environ['TORCH_HOME'] = cache_dir
    print(f"Using TORCH_HOME: {cache_dir}")
    torch.hub.load(
        repo_or_dir='snakers4/silero-vad',
        model='silero_vad',
        force_reload=False,
        onnx=False,
        trust_repo=True
    )
    print("Silero VAD download successful.")
except Exception as e:
    print(f"Error downloading Silero VAD: {e}")
    exit(1)
EOF

# <<<--- faster-whisper Pre-download --->>>
ARG STT_MODEL=medium.en
ARG STT_REALTIME_MODEL=medium.en
ARG STT_USE_MAIN_MODEL_FOR_REALTIME=true
ENV STT_MODEL=${STT_MODEL}
ENV STT_REALTIME_MODEL=${STT_REALTIME_MODEL}
ENV STT_USE_MAIN_MODEL_FOR_REALTIME=${STT_USE_MAIN_MODEL_FOR_REALTIME}
RUN echo "Preloading faster_whisper models (main=${STT_MODEL}, realtime=${STT_REALTIME_MODEL}, share_realtime=${STT_USE_MAIN_MODEL_FOR_REALTIME})" && \
    python3 <<EOF
import os
import faster_whisper

main_model = os.getenv("STT_MODEL", "medium.en")
realtime_model = os.getenv("STT_REALTIME_MODEL", main_model)
share_realtime = os.getenv("STT_USE_MAIN_MODEL_FOR_REALTIME", "true").strip().lower() in {"1", "true", "yes", "on"}

models_to_preload = [main_model]
if not share_realtime and realtime_model != main_model:
    models_to_preload.append(realtime_model)

for model_name in models_to_preload:
    print(f"Downloading STT model: {model_name}")
    faster_whisper.WhisperModel(model_name, device="cpu")

print("STT model download successful.")
EOF

# <<<--- SentenceFinishedClassification Pre-download --->>>
RUN echo "Preloading SentenceFinishedClassification model..." && \
    # Note: Downloads happen as root
    python3 -c "from transformers import DistilBertTokenizerFast, DistilBertForSequenceClassification; \
                print('Downloading tokenizer...'); \
                tokenizer = DistilBertTokenizerFast.from_pretrained('KoljaB/SentenceFinishedClassification'); \
                print('Downloading classification model...'); \
                model = DistilBertForSequenceClassification.from_pretrained('KoljaB/SentenceFinishedClassification'); \
                print('Model downloads successful.')" \
    || (echo "Sentence Classifier download failed" && exit 1)

# <<<--- spaCy en_core_web_sm Pre-download --->>>
RUN echo "Preloading spaCy en_core_web_sm model..." && \
    python3 -m spacy download en_core_web_sm && \
    python3 -c "import spacy; nlp = spacy.load('en_core_web_sm'); print('spaCy model loaded successfully.')" \
    || (echo "spaCy model download failed" && exit 1)

# Ensure directories are owned by appuser - This prepares the image layers correctly
# The entrypoint will handle runtime permissions for volumes/cache
RUN mkdir -p /home/appuser/.cache && \
    chown -R appuser:appgroup /app && \
    chown -R appuser:appgroup /home/appuser

# Copy and set permissions for entrypoint script
COPY --chown=1001:1001 entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Copy the application code last so source edits do not invalidate model layers
COPY --chown=1001:1001 code/ /app/code/

# --- REMOVED USER appuser --- The container will start as root.

# --- Keep ENV vars ---
ENV CUDA_HOME=/usr/local/cuda
ENV PATH="${CUDA_HOME}/bin:${PATH}"
ENV LD_LIBRARY_PATH="${CUDA_HOME}/lib64:${LD_LIBRARY_PATH}"
ENV PYTHONUNBUFFERED=1
ENV MAX_AUDIO_QUEUE_SIZE=50
ENV LOG_LEVEL=INFO
ENV NVIDIA_VISIBLE_DEVICES=all
ENV NVIDIA_DRIVER_CAPABILITIES=compute,utility
ENV RUNNING_IN_DOCKER=true
ENV DS_BUILD_OPS=1
ENV DS_BUILD_CPU_ADAM=0
ENV DS_BUILD_FUSED_ADAM=0
ENV DS_BUILD_UTILS=0
ENV DS_BUILD_TRANSFORMER=1

# Set working directory for the application
WORKDIR /app/code

# Expose the port the FastAPI application runs on
EXPOSE 8000

# Set the entrypoint script - This runs as root
ENTRYPOINT ["/entrypoint.sh"]
# Define the default command - This is passed as "$@" to the entrypoint script
CMD ["python", "-m", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
