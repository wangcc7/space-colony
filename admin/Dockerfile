FROM docker.io/makerdong/python-cn:3.9-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com
COPY main.py .
EXPOSE 58018
CMD ["sh", "-c", "sleep 15 && python main.py"]
