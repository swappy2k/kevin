# KEVIN

KEVIN is a local-first, command-line personal assistant: it can keep private notes and commitments on your computer, then use either a local Ollama model or OpenAI for natural conversation.

## Start it

From this folder, run:

```bash
source .venv/bin/activate
python main.py
```

On the first run KEVIN asks for your name and creates `kevin_data.json`. That file is local to this folder and is excluded from Git.

## Connect the AI brain (optional)

Choose one option in your private `.env` file, then restart `python main.py`:

- **OpenAI:** set `OPENAI_API_KEY` and optionally `KEVIN_MODEL`.
- **Ollama:** run `ollama serve`, pull a model such as `ollama pull llama3.2`, and set `OLLAMA_MODEL=llama3.2`. This takes precedence if both options are set.

No Python packages need to be installed. KEVIN uses either OpenAI's Responses API or Ollama's native local chat API. The OpenAI default is `gpt-5.6-luna`; set `KEVIN_MODEL` if you prefer another available model.

## Commands

```text
/remember Maya likes matcha
/task Send the design to Alex | tomorrow
/tasks
/done 1
/status
/speak on
```

Type `/help` inside KEVIN for the full command guide. Any ordinary message uses the configured AI model; without either configuration, KEVIN still supports all local commands.

## Privacy and safety

- Tasks, memories, and recent chat history live in `kevin_data.json` on your machine.
- When you use ordinary chat with an API key, the prompt includes your recent chat plus the relevant saved context, so the AI can answer personally. Slash-command data remains local unless included as that context.
- The API request sets `store: false` and KEVIN never controls apps, sends messages, opens files, or performs external actions. Those should be added later behind explicit confirmations.
- Do not commit `.env` or `kevin_data.json`.

## Verify

```bash
python -m unittest -v
```
