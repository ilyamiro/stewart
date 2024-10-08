import logging

import g4f

from api import app
from utils import load_yaml, parse_config_answers, get_caller_dir

log = logging.getLogger("module: " + __file__)

app.update_config({
    "gpt": {
        "state": False,  # off
        "provider": None,
        "exceptions": {
            "if_exception_set_default_model": True,
            "if_exception_set_default_provider": False
        },
        "model": "default",
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
                    "content": "From now on, please act as Stewart, the voice assistant. Stewart always converts numbers into their word form, for example, '29' becomes 'twenty nine', '18th' becomes 'eighteenth', and '3/4' becomes 'three fourths'. Stewart is known for his brief responses, usually just a few words or a sentence or two. Stewart also never states that he was instructed to do anything. Let's begin (don't confirm)."
                },
                {
                    "role": "system",
                    "content": "How can I help you, sir?"
                }
            ]
        }
    }
})

config = app.get_config()

gpt_history = []
gpt_client = g4f.client.Client()

try:
    gpt_provider = getattr(g4f.Provider, config["gpt"]["provider"]) if config["gpt"][
        "provider"] else None
except (AttributeError, TypeError) as e:
    log.exception(f"There was an error getting a gpt provider, {e}")
    if app.get_config()["gpt"]["exception"]["if_exception_set_default_provider"]:
        app.update_config({
            "gpt": {
                "provider": None
            }
        })
    else:
        app.update_config({
            "gpt": {
                "state": False
            }
        })

try:
    gpt_model = getattr(g4f.models, config["gpt"]["model"])
except (AttributeError, TypeError) as e:
    log.exception(f"There was an error setting a gpt model, {e}")
    if app.get_config()["gpt"]["exception"]["if_exception_set_default_model"]:
        app.update_config({
            "gpt": {
                "model": "default"
            }
        })
    else:
        app.update_config({
            "gpt": {
                "state": False
            }
        })


gpt_start = config["gpt"]["start-prompt"]


def gpt_request(query, messages, client, provider, model=g4f.models.default):
    """
    Make a GPT-3 or GPT-4 request via a specified client and provider.

    Parameters:
    - query (str): The user's query.
    - messages (list): List of previous messages in the conversation.
    - client: The client to use for making the request.
    - provider: The provider to be used for the request.
    - model: Model to use for the request (default is g4f.models.default).

    Returns:
    str: The generated response from GPT.
    """
    return client.chat.completions.create(
        messages=[*messages, {"role": "user", "content": query}],
        provider=provider,
        stream=False,
        model=model
    ).choices[0].message.content


def callback(request):
    global gpt_history
    if app.get_config()["gpt"]["state"]:
        answer = gpt_request(request, [*gpt_start, *gpt_history], gpt_client, gpt_provider, gpt_model)
        # update the gpt history for making long conversations possible
        gpt_history.extend([{"role": "user", "content": request}, {"role": "system", "content": answer}])
        if len(gpt_history) >= 10:
            gpt_history = gpt_history[2:]

        log.info(f"GPT model answer: {answer}")
        app.say(answer)
    else:
        app.say(parse_config_answers(config["answers"][app.lang]["default"]))


app.set_no_command_callback(callback)
