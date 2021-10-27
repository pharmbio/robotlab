FROM python:3.10
WORKDIR /usr/src/app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir gunicorn
COPY . .
EXPOSE 5000
ENV VIABLE_NO_HOT true
RUN ["sh", "-c", "head -c32 /dev/random | base64 > .viable-secret"]
ENTRYPOINT gunicorn --bind 0.0.0.0:5000 protocol_vis:app --threads 100 --workers 4


