"""creating the boto3 client that will connect to aws w our credentials an return running sessions"""

from functools import lru_cache

import boto3
from botocore.config import Config

from dosimeter.config.settings import get_settings


@lru_cache(maxsize=1)
def get_session() -> boto3.Session:
    """
    ONE SHARED AWS session for the entire app
    """

    settings = get_settings()
    return boto3.Session(profile_name=settings.aws_profile, region_name=settings.aws_region)


@lru_cache(maxsize=1)
def client_config() -> Config:
    """every AWS call gives up after the per-call HTTP timeout from settings"""

    timeout = get_settings().bounds.per_call_http_timeout_seconds
    return Config(connect_timeout=timeout, read_timeout=timeout)


@lru_cache(maxsize=None)
def get_client(service_name: str):
    """return a boto3 client"""

    return get_session().client(service_name, config=client_config())
