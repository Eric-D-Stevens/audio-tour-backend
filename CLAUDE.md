# TensorTours — Backend

Python 3.12 AWS Lambda backend serving the TensorTours API.

## Tech Stack

- **Python** 3.12
- **Pydantic v2** — data validation and models
- **boto3** — AWS SDK
- **Deployment target:** AWS Lambda (serverless)

## Package Structure

Src-layout with namespace `tensortours`:

```
audio-tour-backend/
├── src/
│   └── tensortours/
│       ├── lambda_handlers/  # One file per Lambda function entry point
│       ├── models/           # Pydantic models (request/response/domain)
│       ├── services/         # Business logic (OpenAI, Polly, Places, etc.)
│       └── ...
├── tests/                    # pytest test suite
├── scripts/                  # One-off utility scripts
├── check.sh                  # Lint + test runner
└── format.sh                 # Auto-formatter
```

## External Services Used

| Service | Purpose |
|---------|---------|
| OpenAI | Tour script generation |
| Google Places | Location and POI data |
| AWS Polly | Text-to-speech (standard) |
| ElevenLabs | Text-to-speech (premium) |
| DynamoDB | Tour data and user tables |
| S3 | Audio file storage |

## Code Style

- **Formatter:** Black (100-character line length)
- **Linter:** flake8
- **Import sort:** isort (black profile)
- **Type checking:** mypy (strict mode)

## Quality Check Commands

```bash
./check.sh              # Run lint + tests (default)
./check.sh --lint-only  # Lint only
./check.sh --test-only  # Tests only
./format.sh             # Auto-format with black + isort
```

## Testing

- Framework: **pytest** with **moto** for AWS service mocking
- Test coverage is currently **minimal** — a comprehensive testing strategy is a future goal
- This is a hobby project in active development; coverage will improve over time
- **Always ask the user** before writing tests alongside new code

## Deployment

Deployments are triggered automatically via **GitHub Actions only**:
1. GitHub Actions builds a Lambda zip
2. Uploads zip to S3
3. Triggers the infrastructure repo to deploy

**Never deploy manually.** Do not run `aws lambda update-function-code` or similar commands.
