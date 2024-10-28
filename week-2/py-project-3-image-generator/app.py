from flask import Flask, request, jsonify, send_from_directory
import os
import openai
from werkzeug.utils import secure_filename
import json

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads/'
app.config['POSTERS_JSON'] = 'posters.json'

if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

openai.api_key = os.getenv('OPENAI_API_KEY')


def generate_poster_prompt(song_title):
    """
    Generate a detailed prompt for creating a meaningful poster based on the song title.
    """
    base_prompt = f"""Create an artistic and meaningful poster design inspired by the song title: "{song_title}"

    The poster should:
    - Capture the emotional essence and main themes of the title
    - Use symbolic imagery and metaphors that relate to the title's meaning
    - Have a cohesive color scheme that matches the mood
    - Include artistic typography that integrates with the overall design
    - Be visually striking and suitable for a large format poster
    - Balance negative space with detailed elements
    - Create a design that works across cultures and languages

    Style: Create a modern, artistic poster with deep symbolic meaning and professional layout."""

    return base_prompt


def save_poster_data(title, image_url):
    # Load existing data
    if os.path.exists(app.config['POSTERS_JSON']):
        with open(app.config['POSTERS_JSON'], 'r') as f:
            posters_data = json.load(f)
    else:
        posters_data = []

    # Add new poster entry
    posters_data.append({"title": title, "image_url": image_url})

    # Save updated data
    with open(app.config['POSTERS_JSON'], 'w') as f:
        json.dump(posters_data, f, ensure_ascii=False, indent=4)


@app.route('/')
def index():
    return send_from_directory('templates', 'index.html')


@app.route('/upload-audio', methods=['POST'])
def upload_audio():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    if file:
        filename = secure_filename(file.filename)
        audio_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(audio_path)

        try:
            with open(audio_path, 'rb') as audio_file:
                transcription = openai.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file
                )

            transcript_text = transcription.text
            print('Transcribed text:', transcript_text)

            # Generate the enhanced prompt for the poster
            poster_prompt = generate_poster_prompt(transcript_text)

            response = openai.images.generate(
                prompt=poster_prompt,
                n=1,
                size='1024x1024',
                model='dall-e-3',
                response_format='url',
            )

            image_url = response.data[0].url
            print('Generated image URL:', image_url)
            # Save metadata to JSON
            save_poster_data(transcript_text, image_url)

            os.remove(audio_path)

            return jsonify({'imageUrl': image_url})

        except Exception as e:
            print('Error processing audio or generating image:', e)
            return jsonify({'error': 'Failed to process audio or generate image.'}), 500


@app.route('/<path:filename>')
def serve_static(filename):
    return send_from_directory('public', filename)


if __name__ == '__main__':
    app.run(port=3000, debug=True)
