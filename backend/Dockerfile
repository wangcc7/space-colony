FROM docker.io/makerdong/python-cn:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com

COPY main.py .

CMD ["sh", "-c", "sleep 10 && uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1"]
