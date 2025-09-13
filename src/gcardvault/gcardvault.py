import os
import glob
import requests
import pathlib
from getopt import gnu_getopt, GetoptError
from xml.etree import ElementTree
from googleapiclient.discovery import build
from dotenv import load_dotenv

from .google_oauth2 import GoogleOAuth2
from .git_vault_repo import GitVaultRepo
from .etag_manager import ETagManager


# Note: OAuth2 auth code flow for "installed applications" assumes the client secret
# cannot actually be kept secret (must be embedded in application/source code).
# Access to user data must be consented by the user and (more importantly) the
# access & refresh tokens are stored locally with the user running the program.
# 
# See https://developers.google.com/identity/protocols/oauth2/native-app
# “Installed apps are distributed to individual devices, and it is assumed
# that these apps cannot keep secrets.”
DEFAULT_CLIENT_ID = "160026605549-ktl7ghvc9gttpa8u902nm65j3tro3119.apps.googleusercontent.com"
DEFAULT_CLIENT_SECRET = "v9IMS-73WqhjbE5TOB5Gz90s"
OAUTH_SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/contacts.readonly",
    "https://www.googleapis.com/auth/carddav",
]

# Note: Technically, CardDAV URLs should be discovered dynamically in very REST-like
# fashion, so these could be subject to change. Risk of that down the road
# is worth the trade-off of using the People API to discover contact list,
# so much simpler to work with than implementing the full DAV/CardDAV flow.
GOOGLE_CARDDAV_ADDRESSBOOK_URI_FORMAT = "https://www.googleapis.com/carddav/v1/principals/{principal}/lists/default/"
GOOGLE_CARDDAV_CONTACT_HREF_FORMAT = "/carddav/v1/principals/{principal}/lists/default/{contact_id}"
CONTACT_RESOURCE_PAGE_SIZE = 500
CARDDAV_REPORT_PAGE_SIZE = 250

COMMANDS = ['sync', 'login', 'authorize', 'noop']

load_dotenv()

dirname = os.path.dirname(__file__)
usage_file_path = os.path.join(dirname, "USAGE.txt")
version_file_path = os.path.join(dirname, "VERSION.txt")


class Gcardvault:

    def __init__(self, google_oauth2=None, google_apis=None):
        self.command = None
        self.user = None
        self.export_only = False
        self.clean = False
        self.conf_dir = os.getenv("GCARDVAULT_CONF_DIR", os.path.expanduser("~/.gcardvault"))
        self.output_dir = os.getenv("GCARDVAULT_OUTPUT_DIR", os.path.join(os.getcwd(), 'gcardvault'))
        self.client_id = DEFAULT_CLIENT_ID
        self.client_secret = DEFAULT_CLIENT_SECRET

        self._repo = None
        self._google_oauth2 = google_oauth2 if google_oauth2 is not None else GoogleOAuth2(
            app_name="gcardvault",
            authorize_command="gcardvault authorize {email_addr}",
        )
        self._google_apis = google_apis if google_apis is not None else GoogleApis()

    def run(self, cli_args):
        if not self._parse_options(cli_args):
            return
        getattr(self, self.command)()

    def noop(self):
        self._ensure_dirs()
        pass

    def sync(self):
        self._ensure_dirs()

        (credentials, _) = self._google_oauth2.get_credentials(
            self._token_file_path(), self.client_id, self.client_secret, OAUTH_SCOPES, self.user)

        if not self.export_only:
            self._repo = GitVaultRepo("gcardvault", self.version(), self.output_dir, [".vcf"])

        contacts = self._get_contacts(credentials)

        if self.clean:
            self._clean_output_dir(contacts)

        contacts_to_update = self._filter_contacts_to_update(contacts)
        if contacts_to_update:
            vcards = self._get_vcards_for_contacts(credentials, contacts_to_update)
            self._save_vcards(contacts_to_update, vcards)
            if self._repo:
                self._repo.add_all_files()

        if self._repo:
            self._repo.commit("gcardvault sync")

    def login(self):
        self._ensure_dirs()
        self._google_oauth2.authz_and_save_token(
            self._token_file_path(), self.client_id, self.client_secret, OAUTH_SCOPES, self.user)

    def authorize(self):
        self._ensure_dirs()
        self._google_oauth2.authz_and_export_token(
            self.client_id, self.client_secret, OAUTH_SCOPES, self.user)

    def usage(self):
        return pathlib.Path(usage_file_path).read_text().strip()

    def version(self):
        return pathlib.Path(version_file_path).read_text().strip()

    def _parse_options(self, cli_args):
        show_help = show_version = False

        try:
            (opts, pos_args) = gnu_getopt(
                cli_args,
                'efc:o:h',
                ['export-only', 'clean',
                    'conf-dir=', 'output-dir=', 'vault-dir=',
                    'client-id=', 'client-secret=',
                    'help', 'version', ]
            )
        except GetoptError as e:
            raise GcardvaultError(e) from e

        for opt, val in opts:
            if opt in ['-e', '--export-only']:
                self.export_only = True
            elif opt in ['-f', '--clean']:
                self.clean = True
            elif opt in ['-c', '--conf-dir']:
                self.conf_dir = val
            elif opt in ['-o', '--output-dir', '--vault-dir']:
                self.output_dir = val
            elif opt in ['--client-id']:
                self.client_id = val
            elif opt in ['--client-secret']:
                self.client_secret = val
            elif opt in ['-h', '--help']:
                show_help = True
            elif opt in ['--version']:
                show_version = True

        if len(opts) == 0 and len(pos_args) == 0:
            show_help = True

        if show_help:
            print(self.usage())
            return False
        if show_version:
            print(self.version())
            return False

        if len(pos_args) >= 1:
            self.command = pos_args[0]
        if len(pos_args) >= 2:
            self.user = pos_args[1].lower().strip()

        if self.command is None:
            raise GcardvaultError("<command> argument is required", "command")
        if self.command not in COMMANDS:
            raise GcardvaultError("Invalid <command> argument", "command")
        if self.user is None:
            raise GcardvaultError("<user> argument is required", "user")
        if len(pos_args) > 2:
            raise GcardvaultError("Unrecognized arguments")

        return True

    def _ensure_dirs(self):
        for dir in [self.conf_dir, self.output_dir]:
            pathlib.Path(dir).mkdir(parents=True, exist_ok=True)
    
    def _token_file_path(self):
        return os.path.join(self.conf_dir, f"{self.user}.token.json")
    
    def _get_contacts(self, credentials):
        contacts = []

        next_page_token = None
        while True:
            resource = self._google_apis.request_contact_list(credentials, page_token=next_page_token)
            self._add_contacts_from_resource(contacts, resource)

            next_page_token = resource.get('nextPageToken')
            if next_page_token is None:
                break

        return contacts

    def _add_contacts_from_resource(self, contacts, resource):
        for connection in resource.get('connections', []):
            contact = self._get_contact_from_connection(connection)
            if contact:
                contacts.append(contact)

    def _get_contact_from_connection(self, connection):
        contact_source = None
        sources = connection.get('metadata', {}).get('sources', [])
        for source in sources:
            if source.get('type') == "CONTACT":
                contact_source = source
                break

        display_name = None
        names = connection.get('names', [])
        for name in names:
            name_source_type = name.get('metadata', {}).get('source', {}).get('type')
            if name_source_type == "CONTACT":
                display_name = name['displayName']
                break

        if contact_source:
            id = contact_source['id']
            etag = contact_source['etag']
            return Contact(id, display_name, self.user, etag)

        return None

    def _clean_output_dir(self, contacts):
        contact_ids = [contact.id for contact in contacts]
        files_on_disk = self._get_vcard_files_on_disk()
        for contact_id in files_on_disk:
            if contact_id not in contact_ids:
                file_name = files_on_disk[contact_id]
                os.remove(os.path.join(self.output_dir, file_name))
                if self._repo:
                    self._repo.remove_file(file_name)
                print(f"Removed file '{file_name}'")

    def _filter_contacts_to_update(self, contacts):
        contacts_to_update = []
        contacts_up_to_date = 0
        etags = ETagManager(self.conf_dir)

        for contact in contacts:
            vcard_file_path = os.path.join(self.output_dir, contact.file_name)

            etag_changed = etags.test_for_change_and_save(contact.id, contact.etag)
            if os.path.exists(vcard_file_path) and not etag_changed:
                contacts_up_to_date += 1
                continue

            contacts_to_update.append(contact)

        print(f"{contacts_up_to_date} contact(s) are up to date")
        print(f"{len(contacts_to_update)} contact(s) need to be updated")

        return contacts_to_update

    def _get_vcards_for_contacts(self, credentials, contacts):
        vcards = {}

        print(f"Downloading vCards for {len(contacts)} contact(s)")

        count = CARDDAV_REPORT_PAGE_SIZE
        start = 0
        while start < len(contacts):
            end = start + count
            contacts_in_batch = contacts[start:end]
            self._get_vcards_for_contacts_batch(credentials, contacts_in_batch, vcards)
            start += count

        return vcards

    def _get_vcards_for_contacts_batch(self, credentials, contacts, vcards):
        ns = {"d": "DAV:", "card": "urn:ietf:params:xml:ns:carddav", }

        carddav_hrefs = [contact.carddav_href for contact in contacts]
        carddav_href_xml_nodes = "<d:href>" + "</d:href><d:href>".join(carddav_hrefs) + "</d:href>"

        request_body = f"""
<card:addressbook-multiget xmlns:d="{ns['d']}" xmlns:card="{ns['card']}" >
    <d:prop>
        <card:address-data />
    </d:prop>
    {carddav_href_xml_nodes}
</card:addressbook-multiget>
"""

        xml = self._google_apis.request_carddav_report(credentials, self.user, request_body)
        multistatus = ElementTree.fromstring(xml)

        for response in multistatus:
            href = response.findtext("d:href", namespaces=ns)

            for propstat in response.findall("d:propstat", namespaces=ns):
                if propstat.findtext("d:status", namespaces=ns) == "HTTP/1.1 200 OK":
                    vcard = propstat.findtext("d:prop/card:address-data", namespaces=ns)
                    if vcard:
                        vcards[href] = vcard

        for contact in contacts:
            if contact.carddav_href not in vcards:
                raise RuntimeError(f"vCard could not be downloaded for contact '{contact.name}'")

    def _save_vcards(self, contacts, vcards):
        files_on_disk = self._get_vcard_files_on_disk()
        for contact in contacts:
            vcard = vcards[contact.carddav_href]
            target_file_path = os.path.join(self.output_dir, contact.file_name)

            existing_file_name = files_on_disk.get(contact.id)
            if existing_file_name and existing_file_name != contact.file_name:
                existing_file_path = os.path.join(self.output_dir, existing_file_name)
                os.rename(existing_file_path, target_file_path)

            with open(target_file_path, 'w') as file:
                file.write(vcard)

            print(f"Saved contact '{contact.name}' to {contact.file_name}")

    def _get_vcard_files_on_disk(self):
        files_on_disk = {}
        files_names = [os.path.basename(file).lower() for file in glob.glob(os.path.join(self.output_dir, "*.vcf"))]
        for file_name in files_names:
            file_name_wo_ext = os.path.splitext(file_name)[0]
            id = file_name_wo_ext.split("_")[-1]
            files_on_disk[id] = file_name
        return files_on_disk


class GcardvaultError(ValueError):
    pass


class Contact():

    def __init__(self, id, name, principal, etag):
        self.id = id
        self.name = name if name else id
        self.principal = principal
        self.etag = etag

        prefix = "contact"
        if name:
            prefix = "_".join(name.strip().lower().split())
        self.file_name = f"{prefix}_{id.lower()}.vcf"

        self.carddav_href = GOOGLE_CARDDAV_CONTACT_HREF_FORMAT.format(
            principal=self.principal,
            contact_id=id,
        )


class GoogleApis():

    def request_contact_list(self, credentials, page_token=None):
        with build('people', 'v1', credentials=credentials) as service:
            return service.people().connections().list(
                resourceName="people/me",
                sources="READ_SOURCE_TYPE_CONTACT",
                personFields="metadata,names",
                sortOrder="FIRST_NAME_ASCENDING",
                pageSize=CONTACT_RESOURCE_PAGE_SIZE,
                pageToken=page_token,
            ).execute()

    def request_carddav_report(self, credentials, principal, request_body):
        url = GOOGLE_CARDDAV_ADDRESSBOOK_URI_FORMAT.format(principal=principal)
        headers = {
            "Authorization": f"Bearer {credentials.token}",
            "Content-Type": "application/xml; charset=utf-8",
        }
        response = requests.request("REPORT", url, headers=headers, data=request_body)
        response.raise_for_status()
        return response.text
