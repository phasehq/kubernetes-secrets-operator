FROM python:3.11.7-alpine3.20

# Set the working directory in the container
WORKDIR /app

# Copy the necessary files
COPY src/ /app/ 
COPY requirements.txt /app/

# Install required Python packages
RUN pip install --no-cache-dir -r /app/requirements.txt

# Create a non-root user
RUN adduser -D operator-usr
USER operator-usr

# Run the operator script using Kopf
CMD ["kopf", "run", "/app/main.py"]
