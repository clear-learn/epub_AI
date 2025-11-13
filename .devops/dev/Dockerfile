# Dockerfile for a slim ai-epub-api production environment

# --- Builder Stage ---
# This stage installs build-time dependencies to compile Python packages.
FROM python:3.13-alpine AS builder

# Install build-time dependencies for packages like lxml and cryptography.
# These are installed as "virtual" packages and will be removed after pip install.
RUN apk add --no-cache --virtual .build-deps \
    gcc \
    musl-dev \
    libxml2-dev \
    libxslt-dev \
    openssl-dev \
    libffi-dev

WORKDIR /app

COPY requirements.txt .
# Install python packages
RUN pip install --no-cache-dir -r requirements.txt


# --- Final Stage ---
# This is the final, slim image. It only contains runtime dependencies.
FROM python:3.13-alpine AS final

# Install runtime dependencies (which are much smaller than build-time ones)
RUN apk add --no-cache \
    libxml2 \
    libxslt

WORKDIR /app

# Copy installed Python packages from the builder stage
COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
# Copy only the application code needed for runtime (thanks to .dockerignore)
COPY app/ app/

EXPOSE 18000

# Command to run the application as a module
CMD ["python3", "dev_main.py"]