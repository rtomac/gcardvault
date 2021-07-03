import os


class ETagManager():

    def __init__(self, conf_dir):
        self._etag_cache_file_path = os.path.join(conf_dir, ".etags")
        self._cache = self._read_cache_file()

    def test_for_change_and_save(self, object_name, etag):
        key = "_".join(object_name.strip().lower().split())
        value = "_".join(etag.strip().strip('"').split())

        if key in self._cache and self._cache[key] == value:
            return False

        self._cache[key] = value
        self._write_cache_file()
        return True

    def _read_cache_file(self):
        cache = {}
        if os.path.exists(self._etag_cache_file_path):
            with open(self._etag_cache_file_path, 'r') as file:
                for line in file:
                    (key, value) = line.split()
                    cache[key] = value
        return cache

    def _write_cache_file(self):
        with open(self._etag_cache_file_path, 'w') as file:
            for key in self._cache:
                value = self._cache[key]
                print(f"{key}\t{value}", file=file)
