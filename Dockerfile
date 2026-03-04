FROM public.ecr.aws/lambda/python:3.12

COPY pyproject.toml ./
COPY src/ src/
RUN pip install . --target "${LAMBDA_TASK_ROOT}" --no-cache-dir

# Default CMD — overridden per-function in CDK
CMD ["tensortours.lambda_handlers.geolocation.handler"]
