# The LangGraph workflow, served the way AgentCore Runtime expects: POST /invocations
# and GET /ping on port 8080.
# The base image is pinned by digest. The digest is a multi-arch index, so the same
# pin builds the arm64 image AgentCore Runtime runs.

# stage 1: build our package into a wheel
FROM python:3.11-slim-bookworm@sha256:a36c24f9cbdf4fd0f52d67f0823eeac19c2028c637cecc392d97f980d4fec56b AS build
COPY pyproject.toml /build/
COPY src /build/src
RUN pip wheel --no-cache-dir --no-deps --wheel-dir /wheels /build

# stage 2: install it and run it as a non-root user
FROM python:3.11-slim-bookworm@sha256:a36c24f9cbdf4fd0f52d67f0823eeac19c2028c637cecc392d97f980d4fec56b
ENV PYTHONUNBUFFERED=1
COPY --from=build /wheels /wheels
RUN pip install --no-cache-dir /wheels/*.whl && rm -rf /wheels && useradd --create-home --uid 10001 dosimeter
USER dosimeter
EXPOSE 8080
CMD ["python", "-m", "dosimeter.runtime.main"]
