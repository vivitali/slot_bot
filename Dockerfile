FROM python:3.13-slim

WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Set environment variables (these will be overridden by deployment)
ENV TELEGRAM_TOKEN=""
ENV VISA_EMAIL=""
ENV VISA_PASSWORD=""
ENV SCHEDULE_ID=""
ENV COUNTRY_CODE="en-ca"
ENV VISA_TYPE="niv"
ENV FACILITY_ID=""
ENV CHECK_INTERVAL="600"
ENV MAX_SUBSCRIBERS="4"
ENV CHAT_ID=""

# Run the bot
CMD ["python", "main.py"]