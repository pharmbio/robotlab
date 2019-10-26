Robot rest-api project

# Requirements
Python version >= 3.6

# Create a virtualenv for your project
virtualenv -p python3 venv
source venv/bin/activate

# Install python requirements
pip3 install -r requirements.txt

# start server
python3 server.py

# look at api in swagger ui
http://localhost:8087/ui/

# example execute program with id=12 on robot
curl -X GET --header 'Accept: application/json' 'http://localhost:8087/execute_prog/12'
