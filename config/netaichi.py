import os

from dotenv import load_dotenv

load_dotenv()

default_pw = os.environ['NETAICHI_DEFAULT_PW']
OGURI_ACCOUNT_ID = os.environ['OGURI_ACCOUNT_ID']
KOMADA_ACCOUNT_ID = os.environ['KOMADA_ACCOUNT_ID']

IS_HEADLESS = False
DB_PATH = 'netaichi2024'
