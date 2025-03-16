
import os
from flask import Flask

app = Flask(__name__)

@app.route('/', methods=['GET'])
def home():
    return "Visa Appointment Checker Bot is running! 🚀"

@app.route('/webhook', methods=['POST'])
def webhook():
    return {'status': 'ok'}

if __name__ == '__main__':
    # Get the port from the environment variable
    port = int(os.getenv('PORT', 8080))
    
    # Start the Flask app - this is critical for Cloud Run
    app.run(host='0.0.0.0', port=port, debug=False)