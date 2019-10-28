# Robot REST-api
This project is built upon the python-flask-swagger REST API framework **connexion**, https://github.com/zalando/connexion

Define your api-endpoints and their mapping to the python functions in `swagger-cobot.yml`

Create your python functions (`cobot.py`)

## Requirements
- Python version >= 3.6
- venv (should be included in Python > 3.3 (if not... `sudo apt install python3.6-venv`)

## Installation and test
```
# Clone
git clone git@github.com:pharmbio/labrobots-restserver.git

cd labrobots-restserver

# Create a virtualenv for your project
python3 -m venv venv
source venv/bin/activate

# Install python requirements
pip3 install -r requirements.txt

# start server
python3 server.py

# look at api in swagger ui
http://localhost:8087/ui/

# example execute program with id=12 on robot
curl -X GET --header 'Accept: application/json' 'http://localhost:8087/execute_prog/12'
```
