# The LangGraph workflow, served the way AgentCore Runtime expects: POST /invocations
# and GET /ping on port 8080. We build the wheel, then run it as a non-root
# user on a base image pinned by digest. 

FROM python:3.11-slim-bookworm@sha256:a36c24f9cbdf4fd0f52d67f0823eeac19c2028c637cecc392d97f980d4fec56b AS build

WORKDIR /build
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1

COPY pyproject.toml ./
COPY src ./src

RUN pip install --no-cache-dir build \
    && python -m build --wheel --outdir /wheels


FROM python:3.11-slim-bookworm@sha256:a36c24f9cbdf4fd0f52d67f0823eeac19c2028c637cecc392d97f980d4fec56b AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=8080

RUN useradd --create-home --uid 10001 dosimeter

COPY --from=build /wheels /wheels
RUN pip install --no-cache-dir /wheels/*.whl && rm -rf /wheels

USER dosimeter
WORKDIR /home/dosimeter

EXPOSE 8080

CMD ["python", "-m", "dosimeter.runtime.main"]
