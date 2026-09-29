# Model Routing

The Office routes work by `LOW`, `MEDIUM`, `HIGH`, and `ESCALATION` complexity. A common local setup is a fast quantized coding model for LOW/MEDIUM, a stronger local reasoning model for HIGH, and an optional frontier endpoint for ESCALATION.

Example profiles are in `examples/model_profiles.json`. Endpoints only need an OpenAI-compatible `/chat/completions` API. API keys are read from environment variables and are not copied into `.office/`.

The model is not the verifier. A larger model may improve proposals, but correctness remains tied to external tests/evidence and immutable gates.
