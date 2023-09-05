FROM python:latest

WORKDIR /root
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .

CMD ["python", "./bot.py"] 
