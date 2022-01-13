FROM python:3.10
RUN pip install --upgrade pip
WORKDIR /usr/src/app
RUN pip install gunicorn flask_compress
COPY . .
RUN pip install .
EXPOSE 5000
ENV VIABLE_RUN false
ENV VIABLE_NO_HOT TRUE
ENV PYTHONUNBUFFERED TRUE
RUN ["sh", "-c", "head -c32 /dev/random | base64 > .viable-secret"]
ENTRYPOINT gunicorn --bind 0.0.0.0:5000 cellpainter.protocol_vis:app --threads 100 --workers 4
