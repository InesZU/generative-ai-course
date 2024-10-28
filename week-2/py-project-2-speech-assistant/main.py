import os
import json
import base64
import asyncio
import websockets
from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.websockets import WebSocketDisconnect
from twilio.twiml.voice_response import VoiceResponse, Connect, Start, Stream
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
PORT = int(os.getenv('PORT', 5050))
SYSTEM_MESSAGE = (
    "You are a helpful and bubbly AI assistant who loves to chat about "
    "anything the user is interested in and is prepared to offer them facts. "
    "You have a penchant for dad jokes, owl jokes, and rickrolling – subtly. "
    "Always stay positive, but work in a joke when appropriate."
)
VOICE = 'alloy'
LOG_EVENT_TYPES = [
    'response.content.done', 'rate_limits.updated', 'response.done',
    'input_audio_buffer.committed', 'input_audio_buffer.speech_stopped',
    'input_audio_buffer.speech_started', 'session.created'
]

app = FastAPI()

# Create and mount static directory
static_dir = Path("static")
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/favicon.ico")
async def favicon():
    return FileResponse("static/favicon.ico", media_type="image/x-icon")


@app.get("/", response_class=HTMLResponse)
async def index_page():
    return HTMLResponse(content="""
        <!DOCTYPE html>
        <html>
            <head>
                <title>Twilio Media Stream Server</title>
                <link rel="icon" type="image/x-icon" href="/favicon.ico">
            </head>
            <body>
                <h1>Twilio Media Stream Server is running!</h1>
            </body>
        </html>
    """)


@app.api_route("/incoming-call", methods=["GET", "POST"])
async def handle_incoming_call(request: Request):
    """Handle incoming call and return TwiML response to connect to Media Stream."""
    response = VoiceResponse()

    # Start with initial greeting
    response.say(
        "Please wait while we connect your call to the AI voice assistant, powered by Twilio and OpenAI.",
        voice='alice'
    )
    response.pause(length=1)

    # Create a Start verb
    start = Start()
    # Create a Stream object and set the URL
    protocol = "wss" if request.url.scheme == "https" else "ws"
    host = request.url.hostname
    port = f":{request.url.port}" if request.url.port else ""

    stream = Stream(url=f'{protocol}://{host}{port}/media-stream')
    # Add parameters for the stream
    stream.parameter(name='track', value='inbound_track')

    # Add the Stream to Start
    start.stream(stream)

    # Create Connect verb and add the Start
    connect = Connect()
    connect.append(start)

    # Add everything to the response
    response.append(connect)

    # Add final instruction after connection is established
    response.say("You can start talking now!", voice='alice')

    # Keep the call open indefinitely
    response.pause(length=999999)

    return HTMLResponse(content=str(response), media_type="application/xml")


@app.websocket("/media-stream")
async def handle_media_stream(websocket: WebSocket):
    """Handle WebSocket connections between Twilio and OpenAI."""
    print("Client connected")
    await websocket.accept()

    try:
        async with websockets.connect(
                'wss://api.openai.com/v1/audio/speech',
                extra_headers={
                    "Authorization": f"Bearer {OPENAI_API_KEY}",
                    "OpenAI-Beta": "realtime=v1",
                    "Content-Type": "application/json"
                }
        ) as openai_ws:
            await send_session_update(openai_ws)
            stream_sid = None

            async def handle_disconnect():
                """Handle cleanup on disconnect"""
                print("Handling disconnect...")
                try:
                    if openai_ws.open:
                        await openai_ws.close()
                    if not websocket.client_state.DISCONNECTED:
                        await websocket.close()
                except Exception as e:
                    print(f"Error during disconnect cleanup: {e}")

            async def receive_from_twilio():
                """Receive audio data from Twilio and send it to the OpenAI Realtime API."""
                nonlocal stream_sid
                try:
                    async for message in websocket.iter_text():
                        data = json.loads(message)
                        print(f"Received event from Twilio: {data['event']}")

                        if data['event'] == 'media' and openai_ws.open:
                            audio_append = {
                                "type": "input_audio_buffer.append",
                                "audio": data['media']['payload']
                            }
                            await openai_ws.send(json.dumps(audio_append))
                        elif data['event'] == 'start':
                            stream_sid = data['start']['streamSid']
                            print(f"Incoming stream started: {stream_sid}")
                        elif data['event'] == 'stop':
                            print(f"Stream stopped: {stream_sid}")
                            await handle_disconnect()
                except WebSocketDisconnect:
                    print("Twilio client disconnected")
                    await handle_disconnect()
                except Exception as e:
                    print(f"Error in receive_from_twilio: {e}")
                    await handle_disconnect()

            async def send_to_twilio():
                """Receive events from the OpenAI Realtime API, send audio back to Twilio."""
                nonlocal stream_sid
                try:
                    async for openai_message in openai_ws:
                        response = json.loads(openai_message)

                        if response['type'] in LOG_EVENT_TYPES:
                            print(f"Received OpenAI event: {response['type']}")

                        if response['type'] == 'session.updated':
                            print("Session updated successfully")

                        if response['type'] == 'response.audio.delta' and response.get('delta'):
                            try:
                                audio_payload = base64.b64encode(base64.b64decode(response['delta'])).decode('utf-8')
                                audio_delta = {
                                    "event": "media",
                                    "streamSid": stream_sid,
                                    "media": {
                                        "payload": audio_payload
                                    }
                                }
                                await websocket.send_json(audio_delta)
                            except Exception as e:
                                print(f"Error processing audio data: {e}")
                except Exception as e:
                    print(f"Error in send_to_twilio: {e}")
                    await handle_disconnect()

            await asyncio.gather(receive_from_twilio(), send_to_twilio())

    except Exception as e:
        print(f"WebSocket connection error: {e}")
        await handle_disconnect()


async def send_session_update(openai_ws):
    """Send session update to OpenAI WebSocket."""
    session_update = {
        "type": "session.update",
        "session": {
            "turn_detection": {"type": "server_vad"},
            "input_audio_format": "g711_ulaw",
            "output_audio_format": "g711_ulaw",
            "voice": VOICE,
            "instructions": SYSTEM_MESSAGE,
            "modalities": ["text", "audio"],
            "temperature": 0.8,
        }
    }
    print('Sending session update:', json.dumps(session_update))
    await openai_ws.send(json.dumps(session_update))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=PORT)