# Later Line

Put a task off. A local open-weight model may replace it with one shorter line. If that line is longer, or it drops the thing the task was about, the line is thrown away and the first 12 words stay.

This is the opposite of a tool that writes the draft for you. The only work it removes is rereading.

## Run

```bash
ollama pull gemma3:1b
python3 later_line.py samples/pile.txt --json run.json --html docs/run.html
```

`--rules-only` skips the model. Tests do not need Ollama:

```bash
python3 -m unittest tests.test_later_line
```

Nothing in the pile is sent anywhere except `127.0.0.1:11434`.

## What gets kept

A model line is kept only when all of these are true:

- it is at most 12 words
- it has fewer words than the task
- it still contains a concrete word from the task

A task that is already 12 words or fewer is not sent to the model.

MIT licensed.
