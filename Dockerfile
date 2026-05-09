# ==========================================================================
#  Books ETL — Custom Airflow image with Playwright + Chromium
# ==========================================================================
#  Base: official Airflow 2.9.2 (Debian bookworm, Python 3.12)
#  Additions:
#    • System libraries required by Chromium (headless)
#    • playwright Python package + chromium browser binary
#    • pandas for data transformation
# ==========================================================================

FROM apache/airflow:2.9.2

# ── Switch to root to install OS-level dependencies ───────────────────────
USER root

# Playwright's Chromium needs these shared libraries on Debian/Ubuntu.
# We install them in one layer to keep the image smaller.
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Core rendering & font libraries
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    libatspi2.0-0 \
    libxshmfence1 \
    libxfixes3 \
    # Fonts so rendered pages don't look broken
    fonts-liberation \
    fonts-noto-color-emoji \
    # wget is handy for debugging inside the container
    wget \
    && rm -rf /var/lib/apt/lists/*

# Create the data directory and ensure the airflow user can write to it
RUN mkdir -p /opt/airflow/data && chown -R airflow:0 /opt/airflow/data

# ── Switch back to the airflow user for pip installs ──────────────────────
USER airflow

# Install Python dependencies (playwright, pandas, etc.)
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Download the Chromium browser binary that Playwright manages
RUN playwright install chromium

# ── Copy project source code into the image ───────────────────────────────
# (We also bind-mount these at runtime via docker-compose for live editing,
#  but baking them in means the image is self-contained for CI/CD.)
COPY dags/    /opt/airflow/dags/
COPY scripts/ /opt/airflow/scripts/
