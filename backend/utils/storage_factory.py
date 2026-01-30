import os
from abc import ABC, abstractmethod
import boto3
from botocore.exceptions import ClientError
from azure.storage.blob import BlobServiceClient

class StorageProvider(ABC):

    @abstractmethod
    def upload(self, local_file_path: str, remote_file_path: str) -> str:
        pass

    @abstractmethod
    def download(self, remote_file_path: str, local_file_path: str):
        pass

    @abstractmethod
    def delete(self, remote_file_path: str):
        pass

    @abstractmethod
    def exists(self, remote_file_path: str) -> bool:
        pass

    @abstractmethod
    def read_bytes(self, remote_file_path: str) -> bytes:
        """Reads the content of a remote file into memory as bytes."""
        pass


class S3StorageProvider(StorageProvider):
    def __init__(self, bucket_name: str, region: str):
        self.s3_resource = boto3.resource('s3')
        self.bucket_name = bucket_name
        self.region = region

    def upload(self, local_file_path: str, remote_file_path: str) -> str:
        s3_object = self.s3_resource.Object(self.bucket_name, remote_file_path)
        s3_object.upload_file(local_file_path)
        return f"https://{self.bucket_name}.s3.{self.region}.amazonaws.com/{remote_file_path}"

    def download(self, remote_file_path: str, local_file_path: str):
        s3_object = self.s3_resource.Object(self.bucket_name, remote_file_path)
        s3_object.download_file(local_file_path)

    def delete(self, remote_file_path: str):
        s3_object = self.s3_resource.Object(self.bucket_name, remote_file_path)
        s3_object.delete()

    def exists(self, remote_file_path: str) -> bool:
        try:
            self.s3_resource.Object(self.bucket_name, remote_file_path).load()
            return True
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                return False
            else:
                raise

    def read_bytes(self, remote_file_path: str) -> bytes:
        s3_object = self.s3_resource.Object(self.bucket_name, remote_file_path)
        return s3_object.get()['Body'].read()

class AzureStorageProvider(StorageProvider):
    def __init__(self, connection_string: str, container_name: str):
        self.blob_service_client = BlobServiceClient.from_connection_string(connection_string)
        self.container_name = container_name

    def upload(self, local_file_path: str, remote_file_path: str) -> str:
        blob_client = self.blob_service_client.get_blob_client(
            container=self.container_name, blob=remote_file_path
        )
        with open(local_file_path, "rb") as data:
            blob_client.upload_blob(data, overwrite=True)
        return blob_client.url

    def download(self, remote_file_path: str, local_file_path: str):
        blob_client = self.blob_service_client.get_blob_client(
            container=self.container_name, blob=remote_file_path
        )
        with open(file=local_file_path, mode="wb") as local_blob:
            download_stream = blob_client.download_blob()
            local_blob.write(download_stream.readall())
    
    def delete(self, remote_file_path: str):
        blob_client = self.blob_service_client.get_blob_client(
            container=self.container_name, blob=remote_file_path
        )
        blob_client.delete_blob()

    def exists(self, remote_file_path: str) -> bool:
        blob_client = self.blob_service_client.get_blob_client(
            container=self.container_name, blob=remote_file_path
        )
        return blob_client.exists()
    
    def read_bytes(self, remote_file_path: str) -> bytes:
        blob_client = self.blob_service_client.get_blob_client(
            container=self.container_name, blob=remote_file_path
        )
        download_stream = blob_client.download_blob()
        return download_stream.readall()

def get_storage_provider(reports_container=False) -> StorageProvider:
    provider = os.environ.get("STORAGE_PROVIDER", "AZURE")

    if provider == "S3":
        return S3StorageProvider(
            bucket_name=os.environ["AMAZON_S3_BUCKET"] if not reports_container else os.environ["AMAZON_S3_BUCKET_REPORTS"],
            region=os.environ["AWS_REGION"]
        )
    elif provider == "AZURE":
        return AzureStorageProvider(
            connection_string=os.environ["AZURE_STORAGE_CONNECTION_STRING"],
            container_name=os.environ["AZURE_STORAGE_CONTAINER_NAME"] if not reports_container else os.environ["AZURE_STORAGE_REPORTS_CONTAINER_NAME"]
        )
    else:
        raise ValueError(f"Unknown storage provider: {provider}")