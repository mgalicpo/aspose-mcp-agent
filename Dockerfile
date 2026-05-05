FROM python:3.12-slim

WORKDIR /app

COPY products.json .
COPY scripts/ scripts/
COPY .env.example .

# No external dependencies — scripts use only stdlib
RUN python -m py_compile scripts/check_nuget.py \
    && python -m py_compile scripts/analyze_release_aspose.py \
    && python -m py_compile scripts/upgrade_product.py

ENV ASPOSE_LLM_TOKEN=""

ENTRYPOINT ["python"]
CMD ["scripts/check_nuget.py"]
