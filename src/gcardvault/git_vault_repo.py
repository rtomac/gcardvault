import os
from git import Repo, exc


class GitVaultRepo():

    def __init__(self, package_name, package_version, dir_path, extensions):
        self._package_name = package_name
        self._extensions = extensions
        self._repo = None
        
        try:
            self._repo = Repo(dir_path)
        except exc.InvalidGitRepositoryError:
            self._repo = Repo.init(dir_path)
            self._repo.config_writer().set_value(self._package_name, 'vault', package_version).release()
            self._add_gitignore()
            print(f"Created {self._package_name} repository")

        is_vault = \
            len(self._repo.config_reader().get_value(self._package_name, 'vault', default='')) > 0
        self._msg_prefix = ""
        self._dry_run = False
        if not is_vault:
            print(f"WARNING: Git repository does not appear to have been "
                f"created by {self._package_name}, no changes will be committed. "
                f"\nTo enable it as a {self._package_name} vault, run:"
                f"\n  cd {dir_path}"
                f"\n  git config --add {self._package_name}.vault {package_version}")
            self._dry_run = True
            self._msg_prefix = "[DRY RUN] "

    def add_file(self, file_name):
        print(f"{self._msg_prefix}Adding {file_name} to {self._package_name} repository")
        if not self._dry_run:
            self._repo.index.add(file_name)

    def add_all_files(self):
        for ext in self._extensions:
            print(f"{self._msg_prefix}Adding all {ext} files to {self._package_name} repository")
            if not self._dry_run:
                self._repo.index.add(f'*{ext}')

    def remove_file(self, file_name):
        print(f"{self._msg_prefix}Removing {file_name} from {self._package_name} repository")
        if not self._dry_run:
            self._repo.index.remove([file_name], working_tree=True)

    def commit(self, message):
        if not self._dry_run:
            changes = self._repo.index.diff(self._repo.head.commit)
            if (changes):
                self._repo.index.commit(message)
                print(f"Committed {len(changes)} revision(s) to {self._package_name} repository")
            else:
                print(f"No revisions to commit to {self._package_name} repository")
        else:
            print(f"{self._msg_prefix}Committing revision(s) to {self._package_name} repository")

    def _add_gitignore(self):
        gitignore_path = os.path.join(self._repo.working_dir, ".gitignore")
        with open(gitignore_path, 'w') as file:
            print('*', file=file)
            print('!.gitignore', file=file)
            for ext in self._extensions:
                print(f'!*{ext}', file=file)
        self._repo.index.add('.gitignore')
        self._repo.index.commit("Add .gitignore")
