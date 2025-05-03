import re
import os
from deep_translator import GoogleTranslator


def extract_code_elements(text):
    pattern = r'`([^`]+)`'

    code_elements = re.findall(pattern, text)

    replaced_text = text
    for i, element in enumerate(code_elements):
        placeholder = f"__CODE_{i}__"
        replaced_text = replaced_text.replace(f'`{element}`', placeholder, 1)

    return replaced_text, code_elements


def restore_code_elements(translated_text, code_elements):
    result = translated_text
    for i, element in enumerate(code_elements):
        placeholder = f"__CODE_{i}__"
        result = result.replace(placeholder, f'`{element}`')
        result = result.replace(placeholder.lower(), f'`{element}`')

    return result


def fix_capitalization(text):
    lines = text.split('\n')
    fixed_lines = []

    for line in lines:
        if not line.strip() or not line.strip().startswith('-'):
            fixed_lines.append(line)
            continue

        parts = line.split(' ')

        result = [parts[0]]

        capitalize_next = False

        for i, word in enumerate(parts[1:], 1):
            if not word:
                result.append(word)
                continue

            if capitalize_next:
                result.append(word)
                capitalize_next = False
            elif i == 1:
                result.append(word)
            elif '.' in word:
                result.append(word.lower())
                capitalize_next = True
            else:
                result.append(word.lower())

        fixed_lines.append(' '.join(result))

    return '\n'.join(fixed_lines)


def translate_text(text, source_lang='en', target_lang='ru'):
    try:
        translator = GoogleTranslator(source=source_lang, target=target_lang)

        lines = text.split('\n')
        translated_lines = []

        if lines and not lines[0].startswith('-'):
            translated_lines.append(lines[0])
            lines = lines[1:]

        for line in lines:
            if not line.strip():
                translated_lines.append(line)
                continue

            if line.strip().startswith('-'):
                prefix = line[:line.find('-') + 1]
                content = line[line.find('-') + 1:].strip()

                translated_content = translator.translate(content)

                if translated_content and len(translated_content) > 1:
                    first_char = translated_content[0].lower()
                    translated_content = first_char + translated_content[1:]

                translated_lines.append(f"{prefix} {translated_content}")
            else:
                translated_lines.append(translator.translate(line))

        translated_text = '\n'.join(translated_lines)

        return fix_capitalization(translated_text)
    except Exception as e:
        print(f"Translation error: {e}")
        return text


def process(content):
    replaced_content, code_elements = extract_code_elements(content)
    translated_content = translate_text(replaced_content)
    final_content = restore_code_elements(translated_content, code_elements)

    return final_content

