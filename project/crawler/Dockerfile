FROM python:3.11-slim
WORKDIR /app

# Install Python dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy the publisher script
COPY publisher.py ./

# Set the command to run the publisher script
CMD ["python", "publisher.py"]
