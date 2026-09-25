"""Dedicated space to load in the ENV file"""

import os
from dotenv import load_dotenv

load_dotenv()

AWS_PROFILE = os.environ["AWS_PROFILE"]
AWS_REGION = os.environ["AWS_REGION"]

CORPUS_BUCKET_NAME = os.environ["AWS_CORPUS_BUCKET_NAME"]
PACKET_BUCKET_NAME = os.environ["AWS_PACKET_BUCKET_NAME"]

BEDROCK_KB_ID = os.environ["BEDROCK_KB_ID"]
EMBED_MODEL_ID = os.environ["BEDROCK_EMBED_MODEL_ID"]

BEDROCK_MODEL_ID = os.environ["BEDROCK_MODEL_ID"]
BEDROCK_MAX_TOKENS = int(os.environ.get("BEDROCK_MAX_TOKENS", "600"))
