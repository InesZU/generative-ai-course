import os
import time
from flask import Flask, request, jsonify, render_template
from werkzeug.utils import secure_filename
from openai import OpenAI
from dotenv import load_dotenv

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['ALLOWED_EXTENSIONS'] = {'pdf'}

# Load environment variables
load_dotenv()

# Initialize OpenAI client
api_key = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=api_key)

# Configuration constants
ASSISTANT_ID = os.getenv('ASSISTANT_ID')  # Move to environment variable
MAX_RETRIES = 10
RETRY_DELAY = 2


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']


def upload_pdf_to_vector_store(file_path):
    try:
        with open(file_path, 'rb') as file:
            file_data = client.files.create(
                file=open(file_path, 'rb'),
                purpose='assistants'
            )

        print(f"File uploaded with ID: {file_data.id}")

        vector_store = client.beta.vector_stores.create(
            name="Document Vector Store"
        )

        vector_store_response = client.beta.vector_stores.files.create(
            vector_store_id=vector_store.id,
            file_id=file_data.id
        )
        print("File added to vector store", vector_store_response)

        client.beta.assistants.update(
            ASSISTANT_ID,
            tool_resources={"file_search": {"vector_store_ids": [vector_store.id]}}
        )

        print(f"Assistant updated with Vector Store ID: {vector_store.id}")
        return vector_store.id

    except Exception as e:
        print(f"Error uploading file or creating vector store: {e}")
        raise


def get_thread():
    try:
        return client.beta.threads.create()
    except Exception as e:
        print(f"Error creating thread: {e}")
        raise


def add_question(thread_id, question):
    try:
        response = client.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=question
        )
        return response
    except Exception as e:
        print(f"Error adding message to thread: {e}")
        raise


def run_assistant(thread_id):
    try:
        return client.beta.threads.runs.create(
            thread_id=thread_id,
            assistant_id=ASSISTANT_ID
        )
    except Exception as e:
        print(f"Error running assistant: {e}")
        raise


def check_status(thread_id, run_id):
    for attempt in range(MAX_RETRIES):
        try:
            run_status = client.beta.threads.runs.retrieve(
                thread_id=thread_id,
                run_id=run_id
            )

            if run_status.status == "completed":
                messages = client.beta.threads.messages.list(thread_id)
                for message in messages.data:
                    if message.role == 'assistant':
                        # Return the first response text
                        return message.content[0].text.value.strip()
            elif run_status.status == "failed":
                raise Exception("Assistant run failed")

            time.sleep(RETRY_DELAY)

        except Exception as e:
            print(f"Error checking status (attempt {attempt + 1}): {e}")
            if attempt == MAX_RETRIES - 1:
                raise

    return None


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    if not allowed_file(file.filename):
        return jsonify({'error': 'Invalid file type'}), 400

    try:
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)

        vector_store_id = upload_pdf_to_vector_store(file_path)
        os.remove(file_path)  # Clean up the temporary file

        if vector_store_id:
            return jsonify({'message': 'File uploaded and processed successfully.'}), 200
        else:
            return jsonify({'error': 'Failed to process file.'}), 500

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/ask', methods=['POST'])
def ask_question():
    try:
        data = request.get_json()
        question = data.get('question')

        if not question:
            return jsonify({'error': 'No question provided'}), 400

        thread = get_thread()
        add_question(thread.id, question)
        run = run_assistant(thread.id)

        response = check_status(thread.id, run.id)

        if response:
            return jsonify({'answer': response}), 200
        else:
            return jsonify({'error': 'No response received from assistant'}), 504

    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    app.run(debug=True, port=3000)
