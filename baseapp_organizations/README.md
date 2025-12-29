fh = None
try:
    fh = file_object.file.open('r+b')
    fh.seek(offset, os.SEEK_SET)
    num_bytes_written = fh.write(bytes)
finally:
    if fh is not None:
        fh.close()
