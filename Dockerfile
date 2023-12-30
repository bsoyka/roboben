# Use the official Python 3.12 image as a base
FROM python:3.12

# Set a working directory in the container
WORKDIR /app

# Copy the poetry configuration files
COPY pyproject.toml poetry.lock* /app/

# Install poetry
RUN pip install poetry

# Configure poetry to not create a virtual environment inside the Docker container
RUN poetry config virtualenvs.create false

# Install dependencies using poetry
RUN poetry install --no-dev --no-interaction --no-ansi

# Copy the bot module into the container
COPY bot /app/bot

# Set the command to run the bot
CMD ["poetry", "run", "python", "-m", "bot"]
