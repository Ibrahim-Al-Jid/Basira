"""Quarantine for a bounded archive. Accepted input uses the existing scan retention."""

import base64
from contextlib import contextmanager
from hashlib import sha256
import os
from tempfile import SpooledTemporaryFile
from uuid import uuid4

from .artifact_review import MAX_ARTIFACT, InputError


class StorageUnavailable(RuntimeError):
    pass


@contextmanager
def quarantine(file, size, digest):
    bucket = os.getenv("MARSAD_INTAKE_S3_BUCKET")
    file.seek(0)
    if not bucket:
        if os.getenv("MARSAD_INTAKE_STORAGE_REQUIRED") == "1":
            raise StorageUnavailable()
        yield file
        return
    try:
        import boto3
        from botocore.config import Config
        from botocore.exceptions import BotoCoreError, ClientError
    except ImportError:
        raise StorageUnavailable() from None

    key = "quarantine/" + uuid4().hex
    checksum = base64.b64encode(bytes.fromhex(digest)).decode("ascii")
    try:
        client = boto3.client("s3", endpoint_url=os.getenv("MARSAD_INTAKE_S3_ENDPOINT"),
                              config=Config(connect_timeout=3, read_timeout=5, retries={"total_max_attempts": 2}))
        client.put_object(Bucket=bucket, Key=key, Body=file, ContentLength=size,
                          ContentType="application/zip", ChecksumSHA256=checksum)
    except (BotoCoreError, ClientError, OSError, ValueError):
        raise StorageUnavailable() from None
    try:
        with SpooledTemporaryFile(max_size=256_000) as verified:
            result = client.get_object(Bucket=bucket, Key=key)
            body = result["Body"]
            try:
                digest_check = sha256()
                for block in body.iter_chunks(chunk_size=65_536):
                    if verified.tell() + len(block) > MAX_ARTIFACT:
                        raise StorageUnavailable()
                    verified.write(block)
                    digest_check.update(block)
                if verified.tell() != size or digest_check.hexdigest() != digest:
                    raise StorageUnavailable()
            finally:
                body.close()
            verified.seek(0)
            yield verified
    except (BotoCoreError, ClientError, OSError):
        raise StorageUnavailable() from None
    finally:
        try:
            client.delete_object(Bucket=bucket, Key=key)
        except (BotoCoreError, ClientError, OSError):
            # The bucket lifecycle expires orphaned quarantine objects.
            pass


def bounded_update(file, digest, block):
    if file.tell() + len(block) > MAX_ARTIFACT:
        raise InputError("حجم الملف تجاوز ٢ ميجابايت.")
    file.write(block)
    digest.update(block)
