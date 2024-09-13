# Hungry Hippo

Event aggregation RAG LLM using Langchain and Ollama.

## Setup
1. Create a copy of template.csv and enter the sources you want to extract info of, if you want to fetch nested links provide a selector for the links of interest
2. Install ollama on your machine, for me the most convenient setup was to install Nvidia container toolkit and run ollama with Docker Compose.
3. Pull the required models: `nomic-embed-text:latest` and `llama3.1`
4. Create a virtual environment and install the required modules in `requirements.txt`
4. Run main.py
5. Enter your questions in the chat (stdin)

## Debug with Langsmith

For debugging the LLM and it's interactions, see [Get started with LangSmith](https://docs.smith.langchain.com/). You'll need to create an account and an API key then set environment variables as needed. Note if you want a free workaround of the quota or want to keep your data on device, you can self host Langsmith.

## Alternatives

If you're considering alternatives to this service consider `perplexity.ai` or OpenWeb UI with web search configured. 

## Issues

### Immediate
1. Cache index and chunks in data directory, rename existing cache directory to web cache.
2. Better parsing of web documents, some docs are extracting chunks with little data, may be specific to my sources
3. Limit chat history to a specific number of tokens to prevent chat history context from occupying too much of the context window.
4. Unit tests for utils, maybe break up into multiple modules. 
5. Insert source URLs for each chunk and have URLs present in the output.
6. Check that URLs from webpages parsed by indexing are present in the chunks.

### Considering
1. Switch approach to an Agent with tools
2. Pre-processing to determine if RAG or other tools are needed to respond to a user's query to prevent unneccessary calls and info
3. Quick doc walkthrough on nvidia container setup and docker compose setup for ollama
4. Additional tools support
    - add Searxng docker container and use searxng for additional web results
    - check event conflicts with nextcloud calendar?
5. Post processing, for each event listed as output, use search results to double check details and modify as needed
6. Support of OpenAI api and a OpenRouter example of HungryHippo

