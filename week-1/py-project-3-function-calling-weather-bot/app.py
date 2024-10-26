import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

assistant_id = os.getenv('ASSISTANT_ID')
thread_id = None

if not assistant_id:
    assistant = client.beta.assistants.create(
        instructions="You are a weather bot. Use the provided functions to get weather information including the "
                     "probability of rain, strong wind or high UV risk. For US locations, use Fahrenheit; for all other "
                     "locations, use Celsius.",
        model="gpt-4-1106-preview",  # Corrected model name
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "get_current_temperature",
                    "description": "Get the current temperature for a specific location",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "location": {
                                "type": "string",
                                "description": "The city and state/country, e.g., San Francisco, CA or London, UK"
                            },
                            "unit": {
                                "type": "string",
                                "enum": ["Celsius", "Fahrenheit"],
                                "description": "The temperature unit to use. Use Fahrenheit for US locations, Celsius for others."
                            }
                        },
                        "required": ["location", "unit"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_rain_probability",
                    "description": "Get the probability of rain for a specific location",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "location": {
                                "type": "string",
                                "description": "The city and state/country, e.g., San Francisco, CA or London, UK"
                            }
                        },
                        "required": ["location"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_UV_risk",
                    "description": "Get the probability of high UV risk for a specific location",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "location": {
                                "type": "string",
                                "description": "The city and state/country, e.g., San Francisco, CA or London, UK"
                            }
                        },
                        "required": ["location"]
                    }
                }
            }
        ]
    )
    assistant_id = assistant.id
else:
    assistant = client.beta.assistants.retrieve(assistant_id)

# Get user input for location
location = input("Enter a location (e.g., San Francisco, CA or London, UK): ")

thread = client.beta.threads.create()
message = client.beta.threads.messages.create(
    thread_id=thread.id,
    role="user",
    content=f"What's the weather forecast for today in {location}?",
)

run = client.beta.threads.runs.create_and_poll(
    thread_id=thread.id,
    assistant_id=assistant_id,
)

tool_outputs = []


# Mock weather data
def get_mock_weather_data(location):
    # Simple logic to determine if location is in US (checking for state code)
    is_us_location = ", " in location and len(location.split(", ")[1]) == 2

    if is_us_location:
        # US location - return Fahrenheit temperatures
        temp = "57"
        unit = "Fahrenheit"
    else:
        # Non-US location - return Celsius temperatures
        temp = "14"
        unit = "Celsius"

    rain_prob = "0.06"
    uv_risk = "0.30"
    return temp, rain_prob, uv_risk, unit


# Check if the run requires tool outputs
if run.status == 'requires_action' and hasattr(run, 'required_action'):
    temp, rain_prob, uv_risk, unit = get_mock_weather_data(location)

    # Loop through each tool in the required action section
    for tool in run.required_action.submit_tool_outputs.tool_calls:
        if tool.function.name == "get_current_temperature":
            tool_outputs.append({
                "tool_call_id": tool.id,
                "output": temp
            })
        elif tool.function.name == "get_rain_probability":
            tool_outputs.append({
                "tool_call_id": tool.id,
                "output": rain_prob
            })
        elif tool.function.name == "get_UV_risk":
            tool_outputs.append({
                "tool_call_id": tool.id,
                "output": uv_risk
            })

    # Submit all tool outputs at once after collecting them in a list
    if tool_outputs:
        try:
            run = client.beta.threads.runs.submit_tool_outputs_and_poll(
                thread_id=thread.id,
                run_id=run.id,
                tool_outputs=tool_outputs
            )
            print("\nProcessing weather data...")
        except Exception as e:
            print("Failed to submit tool outputs:", e)
    else:
        print("No tool outputs to submit.")

if run.status == 'completed':
    messages = client.beta.threads.messages.list(
        thread_id=thread.id
    )
    # Process messages
    for message in messages.data:
        if message.role == "assistant":
            for content in message.content:
                if content.type == 'text':
                    print("\nWeather Forecast:", content.text.value)
else:
    print("Run status:", run.status)