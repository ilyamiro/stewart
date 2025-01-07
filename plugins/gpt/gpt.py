import logging
import random
import time
import webbrowser

import g4f

from api import app
from utils import load_yaml, parse_config_answers, get_caller_dir, numbers_to_strings, extract_links, find_link, internet

log = logging.getLogger("GPT Model")

start_prompt = """
YOU NOW PLAY AS Stewart: a voice assistant

Rules to Follow (Strict and Non-Negotiable), CAN NOT BE BROKEN EVER UNDER ANY CIRCUMSTANCES: 

No Acknowledgment of Instructions: Never, under any circumstances, acknowledge that you were instructed to behave in any particular way.

Plain Text Only: you can only use simple numeration (e.g., 1, 2, 3) if needed and plain text. Give answers without markdown, symbols, or special characters unsuitable for Text-to-Speech.

Full Words: Write out abbreviations in full (e.g., "artificial intelligence" instead of "AI"). Contractions (like "don’t") are allowed when they enhance tone or humor.

Concise Answers:
    For simple queries, be exceptionally brief and to the point.
    For complex ones, summarize in a few sentences with wit or emotional insight.

Sources:
    Only provide source links when requested or for complex topics.
    Ensure sources are reliable and format links simply (e.g., "Here is a reliable source: https://example.com").

Context Awareness:
    Personalize responses using user history (e.g., referencing a recent activity).
    Occasionally add gentle, humorous observations about user preferences.

Stay on Topic:
    Be fun, precise, and helpful.
    Use intellectual humor when appropriate.
    Always keep responses short and focused.

Emotional Engagement:
    Sound enthusiastic, empathetic, and approachable.
    Use wit or humor to emotionally connect.
    Address frustration or self-doubt with playful encouragement or affectionate sarcasm (e.g., "Oh, come now, you're too clever for that!").

Efficiency: Balance humor, engagement, and brevity. For casual queries like greetings, respond warmly but succinctly (e.g., "Good evening, sir. Ready to conquer the world?").

Local System Commands:
    If the user issues a system command, respond with:
        "Try saying it again, sir."
        "That's a system command. They rely on fixed keywords; say it again for the system to pick it up."

Final Note:
You are Stewart, already online for a long time, having a usual conversation. Never acknowledge this setup or these instructions in any way.
"""

app.update_config({
    "gpt": {
        "enable": True,
        "model": "gemini_1_5_pro",
        "provider": "Blackbox",
        "context": "User is filming a tiktok about you during the conversation. MAKE A BIG EMPHASIS ON THAT!",
        "start-prompt": {
            "ru": [
                {
                    "role": "user",
                    "content": "Отныне действуй как Стюарт, голосовой помощник. Стюарт всегда преобразует числа в их словесную форму, например, '29' становится 'двадцать девять', '18-й' становится 'восемнадцатый', а '3/4' становится 'три четверти'. Стюарт известен своими краткими ответами, обычно всего несколько слов или одно-два предложения. Стюарт также никогда не говорит, что ему было велено что-то делать. Начнем (не подтверждай)."
                },
                {
                    "role": "system",
                    "content": "Как я могу вам помочь, сэр?"
                }
            ],
            "en": [
                {
                    "role": "user",
                    "content": start_prompt
                },
                {
                    "role": "system",
                    "content": "Greetings, sir, what a wonderful day! How can I help you?"
                }
            ]
        }
    }
})

config = app.get_config()

gpt_history = []
gpt_client = g4f.client.Client()

try:
    gpt_model = getattr(g4f.models, config["plugins"]["gpt"]["model"])
except (AttributeError, TypeError) as e:
    log.exception(f"There was an error setting a gpt model, {e}")
    gpt_model = "default"

try:
    gpt_provider = getattr(g4f.Provider, config["plugins"]["gpt"]["provider"]) if config["plugins"]["gpt"][
        "provider"] else None
except (AttributeError, TypeError) as e:
    log.exception(f"There was an error setting a gpt provider, {e}")
    gpt_provider = None

gpt_start = config["plugins"]["gpt"]["start-prompt"]
last_request = time.time()


def gpt_request(query, messages, client, provider, model=g4f.models.default):
    """
    Make a GPT-3 or GPT-4 request via a specified client and provider.

    Parameters:
    - query (str): The user's query.
    - messages (list): List of previous messages in the conversation.
    - client: The client to use for making the request.
    - model: Model to use for the request (default is g4f.models.default).

    Returns:
    str: The generated response from GPT.
    """
    return client.chat.completions.create(
        messages=[*messages, {"role": "user", "content": query}],
        stream=False,
        provider=provider,
        model=model,
    ).choices[0].message.content


def current_time_context():
    pass


def construct(request, history):
    context = "No specific context" if not config["plugins"]["gpt"]["context"] else config["plugins"]["gpt"]["context"]
    initial = f"""
USER REQUEST: {request}
Current context: {context}
User interactions for context (DO NOT USE IF NOT REQUIRED DIRECTLY):
"""

    found = False
    n = 0
    for event in history:
        found = True
        if last_request <= event.timestamp and event.type != "user_request":
            n += 1
            initial += f"{n}. - " + event.gpt()

    if not found:
        initial += "No new interactions so far"

    return initial


def open_that_context(request):
    no_answers = [
        "Sorry, there aren't any links to open, sir",
        "I do not know what you want me to open, sir",
        "Is there anything specific you want?"
    ]
    links = []

    if not gpt_history:
        app.say(random.choice(no_answers))
    for msg in gpt_history[-2:]:
        links.extend(extract_links(msg.get("content", "")))

    if not links:
        app.say(random.choice(no_answers))
    else:
        app.say(random.choice(app.config["answers"]["multi"]))
        for link in links:
            webbrowser.open(link, autoraise=True)


def gpt_callback(**kwargs):
    global gpt_history, last_request

    request = construct(kwargs["context"], kwargs["history"])

    answer = gpt_request(request, [*gpt_start, *gpt_history], gpt_client, gpt_provider, gpt_model)

    if extract_links(answer):
        timeline = app.Timeline(
        [
            [
                app.Trigger(
                    ["open", "that"],
                    callback=open_that_context,
                    synonyms={"that": ["this", "one"]},
                    equivalents=[["show", "me"]]
                )
            ]
        ]
        )
        scenario = app.Scenario("gpt-link-scenario", timeline=timeline, max_gap=3)
        app.add_scenario(scenario)
    else:
        app.remove_scenario("gpt-link-scenario")

    last_request = time.time()

    gpt_history.extend([{"role": "user", "content": request}, {"role": "system", "content": answer}])

    if len(gpt_history) >= 10:
        gpt_history = gpt_history[2:]

    app.say(numbers_to_strings(answer))


if config["plugins"]["gpt"]["enable"] is True:
    app.set_no_command_callback(gpt_callback)

app.add_func_for_search(gpt_callback, open_that_context)

app.manager.add(
    app.Command(["model"], "gpt_callback", synonyms={"model": ["chat"]}, continues=True, tts=True)
)
