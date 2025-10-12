FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libsm6 \
    libxext6 \
    libgl1 \
    libsndfile1 \
    libjpeg-dev \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

# Install uv (for dependency management)
RUN pip install --no-cache-dir uv

# Copy dependency file and install Python packages
COPY pyproject.toml ./
COPY uv.lock ./

RUN uv sync --frozen --no-dev

# Copy project source code
COPY . .

# Expose port (adjust if needed)
EXPOSE 8000

CMD ["uv", "run", "main_dup.py"]