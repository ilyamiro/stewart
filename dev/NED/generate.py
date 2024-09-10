import g4f.models
from g4f.client import Client


with open("annotations-en.txt", "r") as file:
    data = "\n".join(set(file.read().split("\n")))


client = Client()
answer = client.chat.completions.create(
    model=g4f.models.default,
    messages=[{"role": "user", "content": f"I am creating a database of requests for named entity recognition. Extend my list by adding 20 more of requests just like this, but with different actions, names and objects, and with different sentence structure. ANSWER ONLY WITH NEW GENERATED SENTENCES EACH ON A NEW LINE NOTHING ELSE: {data} "}]
).choices[0].message.content

print(answer)

with open("annotations-en.txt", "w") as file:
    file.write(answer)