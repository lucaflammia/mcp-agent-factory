---
estimated_steps: 1
estimated_files: 1
skills_used: []
---

# T01: Add ProviderNotConfiguredError and provider key validation

Add a ProviderNotConfiguredError exception class and a _validate_provider() function in gateway/app.py that checks the API key env var for explicitly requested providers (openai→OPENAI_API_KEY, anthropic→ANTHROPIC_API_KEY, gemini→GEMINI_API_KEY) and raises the error if missing. ollama needs no key — never raises.

## Inputs

- `gateway/app.py current dispatch structure`
- `router.py provider names`

## Expected Output

- `ProviderNotConfiguredError class in app.py`
- `_validate_provider() function`

## Verification

Unit test: _validate_provider('openai') with no OPENAI_API_KEY set raises ProviderNotConfiguredError; _validate_provider('ollama') never raises.
