from django.core.files.storage import FileSystemStorage


class PrivateFileSystemStorage(FileSystemStorage):
    """Files under MEDIA_ROOT that are only ever streamed through an authorized view."""

    def url(self, name: str | None) -> str:
        raise NotImplementedError("Private media has no public URL")


_private_storage = PrivateFileSystemStorage(
    file_permissions_mode=0o640, directory_permissions_mode=0o750
)


def private_media_storage() -> PrivateFileSystemStorage:
    return _private_storage
