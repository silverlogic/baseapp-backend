ARG PYTHON_VERSION=3.11
FROM python:${PYTHON_VERSION}-slim-trixie

ENV DEBIAN_FRONTEND=noninteractive

# Copy from the cache instead of linking since it's a mounted volume
ENV UV_LINK_MODE=copy

# Disable Python downloads, because we want to use the system interpreter
# across images. If using a managed Python version, it needs to be
# copied from the build image into the final image;
ENV UV_PYTHON_DOWNLOADS=0

# Ensure installed tools can be executed out of the box
ENV UV_TOOL_BIN_DIR=/usr/local/bin

# Set venv path
ENV UV_PROJECT_ENVIRONMENT=/opt/venv
ENV PATH="$UV_PROJECT_ENVIRONMENT/bin:$PATH"

RUN apt-get update -qq && \
    apt-get install -y --no-install-recommends \
    libjpeg62-turbo libjpeg62-turbo-dev libfreetype-dev zlib1g-dev \
    libgeos-dev libgeos3.13.1 libgeos-c1t64 gdal-bin \
    proj-bin libproj-dev libproj25 \
    locales -qq \
    gettext \
    wget \
    git \
    ca-certificates \
    apt-transport-https \
    gnupg && \
    wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub \
      | gpg --dearmor -o /etc/apt/keyrings/google-chrome.gpg && \
    echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/google-chrome.gpg] https://dl.google.com/linux/chrome/deb/ stable main" \
      > /etc/apt/sources.list.d/google-chrome.list && \
    apt-get update -y && \
    apt-get install -y --no-install-recommends google-chrome-stable && \
    rm -rf /var/lib/apt/lists/*

RUN mkdir -p /usr/src/app

COPY . /usr/src/app

WORKDIR /usr/src/app

RUN git config --global --add safe.directory /usr/src/app

# Install uv and sync dependencies (all extras + dev for tests)
COPY --from=ghcr.io/astral-sh/uv:0.10.9 /uv /uvx /bin/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --python "${PYTHON_VERSION}" --frozen --no-install-project --no-editable --group dev

EXPOSE 8000
CMD ["sleep", "infinity"]
