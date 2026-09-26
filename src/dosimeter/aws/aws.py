"""creating the boto3 client that will connect to aws w our credentials an return running sessions"""

from functools import lru_cache

import boto3

from dosimeter.config.settings import get_settings


@lru_cache(maxsize=1)
def get_session() -> boto3.Session:
    """
    ONE SHARED AWS session for the entire app
    """

    settings = get_settings()
    return boto3.Session(profile_name=settings.aws_profile, region_name=settings.aws_region)


@lru_cache(maxsize=None)
def get_client(service_name: str):
    """return a boto3 client"""

    return get_session().client(service_name)
