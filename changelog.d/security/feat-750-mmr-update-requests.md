- MMR screenshots are private: nginx serves no media path, and files are streamed only
  to the requesting member and the staff who can review the request
  (`private, no-store`, `nosniff`, sandboxed). Uploads are decoded, size and pixel
  checked, and re-encoded without EXIF or other metadata under random file names.
