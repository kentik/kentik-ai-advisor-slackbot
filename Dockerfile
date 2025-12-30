FROM python:3.12-slim-bookworm

# Install UV package manager
RUN pip install --no-cache-dir uv

# Create non-root user
RUN useradd -m -u 1000 slackbot

# Set working directory
WORKDIR /app

# Copy project files
COPY pyproject.toml ./
COPY README.md ./
COPY ai_advisor_slackbot/ ./ai_advisor_slackbot/

# Install dependencies using UV
RUN uv pip install --system --no-cache -e .

# Create directory for database
RUN mkdir -p /app/data && chown -R slackbot:slackbot /app

# Switch to non-root user
USER slackbot

# Run the application
CMD ["ai-advisor-slackbot"]
