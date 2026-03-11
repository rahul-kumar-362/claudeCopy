import os
import json
from dotenv import load_dotenv
from google import genai

load_dotenv()
client = genai.Client()
hist = [
    {"role": "user", "parts": [{"text": "Hello, remember the word BUMBLEBEE"}]},
    {"role": "model", "parts": [{"text": "I will remember the word BUMBLEBEE."}]}
]
chat = client.chats.create(model="gemini-2.5-flash", history=hist)
resp = chat.send_message("What was the word?")
print(resp.text)
