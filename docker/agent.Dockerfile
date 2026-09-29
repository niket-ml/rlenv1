FROM python:3.11-slim-bookworm

RUN python -m pip install --no-cache-dir \
    jsonschema==4.26.0 \
    numpy==2.4.6 \
    pandas==3.0.5 \
    scikit-learn==1.9.0 \
    scipy==1.17.1

WORKDIR /workspace

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

CMD ["tail", "-f", "/dev/null"]
