# OpenBot Guide

OpenBot is the chat app inside OpenNet. It answers questions by searching the
documents in its knowledge folder rather than by guessing.

## How it answers

1. Your question is split into keywords.
2. Every document in the knowledge folder is read and split into overlapping
   chunks of roughly 700 characters.
3. Each chunk is scored by how much of your question it covers.
4. Document titles are also compared against your question, so asking for a file
   by name works too.
5. The highest scoring chunk is returned, together with the name of the document
   it came from, which the chat shows as a source line.

If nothing matches, OpenBot says so plainly instead of inventing an answer.

## Supported files

Text files are read directly: `.txt`, `.md`, `.markdown`, `.rst`, `.csv` and
`.json`. PDF files are read with the `pypdf` library. Any other file type is
ignored.

## The knowledge folder

By default OpenBot reads the `docs` folder that ships with the repository. Point
it somewhere else by setting the `OPENBOT_DOCS_DIR` environment variable:

    OPENBOT_DOCS_DIR=/path/to/my/documents python app.py

Parsed documents are cached in memory. The cache invalidates automatically when
a file in the folder is added, edited or removed, so there is no need to restart
the server after changing a document.

## The API

The chat page calls a JSON endpoint. You can call it directly:

    curl -X POST http://localhost:5000/openbot/api \
         -H "Content-Type: application/json" \
         -d '{"question": "what is OpenNet?"}'

A successful reply looks like:

    {
      "answer": "...the matching passage...",
      "source": "opennet-overview.txt",
      "matches": [ ... ]
    }

A malformed or empty request returns HTTP 400 with an `error` field explaining
what was wrong, never a 500.

## Voice input

The microphone button uses the browser's Web Speech API. It is disabled
automatically in browsers that do not support it.
