FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# garrison-sdk, garrison-anvil and garrison-forge come from PyPI via requirements.txt
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002"]
