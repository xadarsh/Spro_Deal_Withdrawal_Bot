# ---------------------------------------------------
# File Name: web_server.py
# Description: Flask web server for Koyeb deployment
# Author: Adarsh
# Created: 2026-01-22
# Version: 1.0.0
# License: MIT License
# ---------------------------------------------------

import os
from flask import Flask, render_template, jsonify

app = Flask(__name__)

@app.route("/")
def welcome():
    """Render the welcome page"""
    return render_template("welcome.html")

@app.route("/health")
def health():
    """Health check endpoint"""
    return jsonify({"status": "ok", "bot": "running"}), 200

@app.route("/status")
def status():
    """Bot status endpoint"""
    return jsonify({
        "status": "active",
        "bot_name": "Spro Deal Withdrawal Bot",
        "version": "1.0.0"
    }), 200

def run_web_server():
    """Run Flask web server"""
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=False)

if __name__ == "__main__":
    run_web_server()
