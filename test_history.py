import os
from dotenv import load_dotenv
from google import genai

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    # use a dummy implementation just to inspect typing if no key
    pass

client = genai.Client(api_key=api_key)
chat = client.chats.create(model="gemini-2.5-flash")
resp = chat.send_message("Hi")
history = chat.get_history()
print(history)
for h in history:
    print(h.model_dump_json(indent=2)) if hasattr(h, 'model_dump_json') else print(h)
