FROM python:3.10-slim

WORKDIR /app

# Install Flask
RUN pip install --no-cache-dir Flask==2.3.3

# Copy just the minimal app
COPY minimal_app.py .

# Expose the port
EXPOSE 8080

# Run the app
CMD ["python", "minimal_app.py"]