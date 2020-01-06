FROM python:3.8

RUN apt-get update && apt-get install -y libgeos-dev && apt-get clean

WORKDIR /usr/src/app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5000

CMD ["python", "-u", "app.py"]
