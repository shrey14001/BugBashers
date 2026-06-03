FROM python:3.12-slim

# System deps for patch CLI + git
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    patch \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Default: run the API
CMD ["uvicorn", "autofix.api.app:app", "--host", "0.0.0.0", "--port", "8000"]