import os

from dotenv import load_dotenv

load_dotenv()

OGURI_GSS_ID = os.environ['OGURI_GSS_ID']
KOMADA_GSS_ID = os.environ['KOMADA_GSS_ID']

JSON_PATH = 'authorized_user.json'
