#!/usr/bin/env python3
import connexion
import logging

logging.basicConfig(level=logging.INFO)
app = connexion.App(__name__)
app.add_api('swagger-incubator.yaml')
# set the WSGI application callable to allow using uWSGI:
# uwsgi --http :8080 -w app
application = app.app

if __name__ == '__main__':
    # run our standalone gevent server
    # other supported options are, flask, tornado, aiohttp
    app.run(port=5001, server='gevent')
