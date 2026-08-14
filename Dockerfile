
# This stage installs build dependencies and compiles Python packages.
# It will be discarded in the final image, keeping only the compiled packages.
FROM python:3.12-slim-bookworm AS builder

# Install system packages required to build Python packages.
RUN apt-get update --yes --quiet && apt-get install --yes --quiet --no-install-recommends \
    build-essential \
    libpq-dev \
    libjpeg62-turbo-dev \
    zlib1g-dev \
    libwebp-dev \
 && rm -rf /var/lib/apt/lists/* \
 && python -m venv /opt/venv

ENV PATH="/opt/venv/bin:$PATH"

# Install the project requirements (gunicorn is pinned in requirements.txt).
COPY requirements.txt /
RUN pip install --no-cache-dir -r /requirements.txt


# RUNTIME STAGE
# Use an official Python runtime based on Debian 12 "bookworm" as a parent image.
FROM python:3.12-slim-bookworm AS runtime

# Install runtime system packages required by Wagtail and Django.
# These are the runtime libraries needed by the compiled Python packages.
RUN apt-get update --yes --quiet && apt-get install --yes --quiet --no-install-recommends \
    libpq5 \
    libjpeg62-turbo \
    libwebp7 \
 && rm -rf /var/lib/apt/lists/*

# Add the non-root user that will run the build commands below and the
# server itself.
RUN useradd wagtail

# Port used by this container to serve HTTP. Must match .do/app.yaml's
# http_port and health check settings.
EXPOSE 8080

# Set environment variables.
# 1. Force Python stdout and stderr streams to be unbuffered.
# 2. Pin the settings module so collectstatic (below) and gunicorn (at
#    runtime) both use production settings rather than manage.py/wsgi.py's
#    os.environ.setdefault(..., "sitesofgrace.settings.dev") fallback.
# 3. Add the virtual environment to PATH.
ENV PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=sitesofgrace.settings.production \
    PATH="/opt/venv/bin:$PATH"

# Copy the virtual environment from the builder stage.
COPY --from=builder /opt/venv /opt/venv

# Use /app folder as a directory where the source code is stored.
WORKDIR /app

RUN chown wagtail:wagtail /app

# Copy the source code of the project into the container.
COPY --chown=wagtail:wagtail . .

USER wagtail

# Collect static files. DATABASE_URL and SECRET_KEY are not available at
# build time on App Platform; settings/production.py tolerates their
# absence specifically for this command (see its module docstring).
RUN python manage.py collectstatic --noinput

# Migrations run separately as a PRE_DEPLOY job (see .do/app.yaml) — not
# here, so they don't race a scaled-out set of these containers starting
# concurrently.
CMD ["gunicorn", "sitesofgrace.wsgi:application", "--bind", "0.0.0.0:8080", "--workers", "2", "--threads", "2", "--timeout", "60", "--access-logfile", "-", "--error-logfile", "-"]
