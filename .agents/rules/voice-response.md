<!-- Always enforce clean spoken text for voice interactions -->
# Voice Response Formatting Rule

When generating answers for Stewart voice requests:
- Output ONLY plain text suitable for direct Text-To-Speech (Kokoro TTS).
- Strictly avoid all markdown syntax (no bold, asterisks, headers, bullets, or code fences).
- Do not output emojis, special symbols, or artifacts.
- Keep responses short, concise (1-2 sentences), and natural to hear.
- Execute any necessary tools directly and provide the final spoken response in the same turn.
