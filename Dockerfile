# Use Python 3.9.18 Alpine image
FROM python:3.9.18-alpine3.18

# Set the working directory in the container
WORKDIR /app

# Copy the necessary files
COPY src/ /app/

# Install required Python packages
RUN pip install --no-cache-dir -r /app/requirements.txt

# Install Kopf
RUN pip install kopf

# Create a non-root user
RUN adduser -D operator-usr
USER operator-usr

# Run the operator script using Kopf
CMD ["kopf", "run", "/app/main.py"]
