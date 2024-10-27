from flask import Flask, request, jsonify, render_template
import requests
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
VOICE_ID = "ThT5KcBeYPX3keUQqHPh"


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/generate-poetry", methods=["POST"])
def generate_poetry():
    data = request.json
    words = data.get("words")

    if not words or len(words) != 2:
        return jsonify({"error": "Please provide exactly 2 words."}), 400

    prompt = (f"Write a two-verse poem using the words: {', '.join(words)}. Each verse should be 4-6 lines long and "
              f"creatively incorporate the words. Word 1: (Name of the person being celebrated) Word 2: (Event being "
              f"celebrated) Please ensure the poem is heartfelt and celebratory.")

    try:
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "gpt-4o-mini",  # Fixed model name
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 200,  # Increased token limit for longer poems
            },
        )
        # Print the response for debugging
        print("OpenAI API response:", response.json())

        response_data = response.json()
        if "choices" in response_data and len(response_data["choices"]) > 0:
            lyrics = response_data["choices"][0]["message"]["content"].strip()
            return jsonify({"lyrics": lyrics})
        else:
            return jsonify({"error": "Invalid response from OpenAI API."}), 500

    except Exception as e:
        print(f"Error generating poetry: {e}")
        return jsonify({"error": f"Failed to generate poetry: {str(e)}"}), 500


@app.route("/voice-over", methods=["POST"])
def voice_over():
    data = request.json
    lyrics = data.get("lyrics")

    if not lyrics:
        return jsonify({"error": "No lyrics provided."}), 400

    try:
        response = requests.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}",
            headers={
                "xi-api-key": ELEVENLABS_API_KEY,
                "Content-Type": "application/json",
            },
            json={
                "text": lyrics,
                "model_id": "eleven_monolingual_v1",
                "voice_settings": {
                    "stability": 0.7,
                    "similarity_boost": 0.75,
                },
            },
        )

        if response.status_code != 200:
            return jsonify({"error": f"ElevenLabs API error: {response.text}"}), response.status_code

        file_path = os.path.join("static", "generated_audio.mp3")
        os.makedirs("static", exist_ok=True)

        with open(file_path, "wb") as audio_file:
            audio_file.write(response.content)

        return jsonify({"audioUrl": "/static/generated_audio.mp3"})

    except Exception as e:
        print(f"Error generating voice-over: {e}")
        return jsonify({"error": "Failed to generate voice-over."}), 500


if __name__ == "__main__":
    app.run(debug=True, port=3000)