import threading
import os
from flask import Flask

app = Flask('')

@app.route('/')
def home():
    return 'Bot is running', 200

def run_bot():
    os.system('python3 bot.py')

threading.Thread(target=run_bot).start()

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))