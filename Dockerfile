FROM python:3.10-alpine

WORKDIR /root
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .

CMD ["python", "./bot.py"] 
