from openai import OpenAI
import os
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("OPENAI_API_KEY")

client = OpenAI(api_key=api_key)


def ask_question(complains):
    messages = [
        {"role": "user", "content": "Your job is to pay very good attention to the user’s complaints and concerns, "
                                    "ask questions if needed, and then provide the best natural remedies "
                                    "in a very short answer."},
        {"role": "user", "content": complains}
    ]
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            max_tokens=100,
        )
        answer = response.choices[0].message.content
        return answer
    except Exception as e:
        return f"An error occurred: {str(e)}"


if __name__ == "__main__":
    print("Hello, my name is Sina, how can I assist you today?")

    # Initialize conversation history with a system message
    messages = [
        {"role": "system", "content": "You are a helpful assistant that provides natural remedies from Ayurveda, "
                                      "TMC or Unani.You are a devoted healer, a good listener, and an expert in your "
                                      "field. Your name is Sina."}
    ]

    while True:
        question = input("You: ")

        if question.lower() in ["exit", "quit", "goodbye"]:
            print("Sina: Goodbye! Feel free to reach out anytime for natural remedies.")
            break

        answer = ask_question(question)
        print("Sina:", answer)