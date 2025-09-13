import os
from git import Repo, exc


class GitVaultRepo():

    def __init__(self, name, dir_path, extensions):
        self._name = name
        self._extensions = extensions
        self._repo = None
        try:
            self._repo = Repo(dir_path)
        except exc.InvalidGitRepositoryError:
            self._repo = Repo.init(dir_path)
            self._add_gitignore()
            print(f"Created {self._name} repository")

    def add_file(self, file_name):
        self._repo.index.add(file_name)

    def add_all_files(self):
        for ext in self._extensions:
            print(f"Adding all {ext} files to {self._name} repository")
            self._repo.index.add(f'*{ext}')

    def remove_file(self, file_name):
        self._repo.index.remove([file_name], working_tree=True)

    def commit(self, message):
        changes = self._repo.index.diff(self._repo.head.commit)
        if (changes):
            self._repo.index.commit(message)
            print(f"Committed {len(changes)} revision(s) to {self._name} repository")
        else:
            print(f"No revisions to commit to {self._name} repository")

    def _add_gitignore(self):
        gitignore_path = os.path.join(self._repo.working_dir, ".gitignore")
        with open(gitignore_path, 'w') as file:
            print('*', file=file)
            print('!.gitignore', file=file)
            for ext in self._extensions:
                print(f'!*{ext}', file=file)
        self._repo.index.add('.gitignore')
        self._repo.index.commit("Add .gitignore")
