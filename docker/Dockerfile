FROM python:3.10
RUN apt-get -y update && apt-get -y upgrade
RUN apt-get install esbuild
RUN pip install --upgrade pip
WORKDIR /usr/src/app
RUN pip install --no-cache-dir gunicorn flask_compress
COPY . .
RUN pip install .
EXPOSE 5000
ENV VIABLE_RUN false
ENV VIABLE_NO_HOT TRUE
ENV PYTHONUNBUFFERED TRUE
RUN ["sh", "-c", "head -c32 /dev/random | base64 > .viable-secret"]
ENTRYPOINT gunicorn --bind 0.0.0.0:5000 cellpainter.protocol_vis_app:app --threads 100 --workers 4
