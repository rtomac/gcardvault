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
            self._repo.config_writer().set_value(self._name, 'vault', True).release()
            self._add_gitignore()
            print(f"Created {self._name} repository")

        self._msg_prefix = ""
        self._dry_run = False
        self._is_vault = \
            self._repo.config_reader().get_value(self._name, 'vault', default=False) == True

        if not self._is_vault:
            print(f"WARNING: current git repository was not created by {self._name}, no changes will be committed")
            self._dry_run = True
            self._msg_prefix = "[DRY RUN] "

    def add_file(self, file_name):
        print(f"{self._msg_prefix}Adding {file_name} to {self._name} repository")
        if not self._dry_run:
            self._repo.index.add(file_name)

    def add_all_files(self):
        for ext in self._extensions:
            print(f"{self._msg_prefix}Adding all {ext} files to {self._name} repository")
            if not self._dry_run:
                self._repo.index.add(f'*{ext}')

    def remove_file(self, file_name):
        print(f"{self._msg_prefix}Removing {file_name} from {self._name} repository")
        if not self._dry_run:
            self._repo.index.remove([file_name], working_tree=True)

    def commit(self, message):
        if not self._dry_run:
            changes = self._repo.index.diff(self._repo.head.commit)
            if (changes):
                self._repo.index.commit(message)
                print(f"Committed {len(changes)} revision(s) to {self._name} repository")
            else:
                print(f"No revisions to commit to {self._name} repository")
        else:
            print(f"{self._msg_prefix}Committing revision(s) to {self._name} repository")

    def _add_gitignore(self):
        gitignore_path = os.path.join(self._repo.working_dir, ".gitignore")
        with open(gitignore_path, 'w') as file:
            print('*', file=file)
            print('!.gitignore', file=file)
            for ext in self._extensions:
                print(f'!*{ext}', file=file)
        self._repo.index.add('.gitignore')
        self._repo.index.commit("Add .gitignore")
