import os
import random
import string


UNIQUE_NAME = "".join(random.choice(string.ascii_lowercase) for i in range(10))
AWS_KEYPAIR = os.getenv("AWS_KEYPAIR", UNIQUE_NAME)
AWS_AMI = os.getenv("AWS_AMI")
AWS_REGION = os.getenv("AWS_REGION")
