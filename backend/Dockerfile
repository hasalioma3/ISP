# Use official Python runtime as a parent image
FROM python:3.9-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set work directory
WORKDIR /app

# Install system dependencies
RUN python -c 'import os, pty, sys; status = pty.spawn(["/bin/sh", "-c", "set -e; export DEBIAN_FRONTEND=noninteractive; apt-get -o Acquire::Retries=2 -o Acquire::http::Timeout=30 -o Acquire::https::Timeout=30 -o Acquire::Progress::Fancy=1 update; apt-get -o Dpkg::Progress-Fancy=1 install -y gcc postgresql-client netcat-openbsd; rm -rf /var/lib/apt/lists/*"]); sys.exit(os.waitstatus_to_exitcode(status))'

# Install python dependencies
COPY requirements.txt /app/
RUN pip install --upgrade pip && pip install -r requirements.txt
RUN pip install gunicorn

# Copy project
COPY . /app/

# Copy entrypoint.sh and make it executable
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Run entrypoint.sh
ENTRYPOINT ["/app/entrypoint.sh"]
