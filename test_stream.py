import os
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()
client = genai.Client()

def get_weather(location: str) -> str:
    return f"The weather in {location} is 72 degrees."

chat = client.chats.create(
    model="gemini-2.5-flash",
    config=types.GenerateContentConfig(
        tools=[get_weather],
        temperature=0.2
    )
)

print("Sending message...")
response = chat.send_message_stream("Call the get_weather tool for SF.")
for chunk in response:
    print("CHUNK:", repr(chunk.text), "CALLS:", chunk.function_calls)
