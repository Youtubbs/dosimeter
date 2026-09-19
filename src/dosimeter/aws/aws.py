"""creating the boto3 client that will connect to aws w our credentials an return running sessions """

import boto3
from functools import lru_cache

from .config import AWS_PROFILE, AWS_REGION

@lru_cache(maxsize=1)
def get_session() -> boto3.Session:
    """
    ONE SHARED AWS session for the entire app
    """

    return boto3.Session(profile_name=AWS_PROFILE, region_name = AWS_REGION)

@lru_cache(maxsize=None)
def get_client(service_name : str):
    """return a boto3 client"""

    return get_session().client(service_name)
