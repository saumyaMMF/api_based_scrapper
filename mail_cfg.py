import os
from dotenv import load_dotenv

load_dotenv()

user = os.getenv("user")
pw = os.getenv("pw")
receiver = os.getenv("receiver").split(",")
receiver_test = os.getenv("receiver_test").split(",")





