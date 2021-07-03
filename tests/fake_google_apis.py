import os
import string
import copy
import json
import random
import hashlib
from xml.etree import ElementTree
from jinja2 import Environment, FileSystemLoader, select_autoescape
from gcardvault.gcardvault import GoogleApis
from jinja2.filters import V


CARDDAV_HREF_FMT = "/carddav/v1/principals/foo.bar@gmail.com/lists/default/{id}"

dirname = os.path.dirname(__file__)
data_dir_path = os.path.join(dirname, "data")


class FakeDataRepo():

    def __init__(self):
        self._list = []
        self._load_fake_data()

    def list(self):
        return self._list

    def _load_fake_data(self):
        fields = None
        with open(os.path.join(data_dir_path, "fake_data.csv"), 'r') as file:
            for line in file:
                values = line.strip().split(',')
                if fields is None:  # first line, load field names
                    fields = values
                else:
                    record = FakeDataRecord()
                    for i in range(len(fields)):
                        record[fields[i]] = values[i]
                    self._list.append(record)


class FakeDataRecord(dict):

    def href(self):
        return CARDDAV_HREF_FMT.format(id=self["id"])

    def etag(self):
        return hashlib.md5(str(self).encode('utf-8')).hexdigest()

    def file_name(self):
        name = f"{self['first_name']} {self['last_name']}"
        prefix = "_".join(name.strip().split()).lower()
        id = self['id'].lower()
        return f"{prefix}_{id}.vcf"

    def vcard(self):
        return """
BEGIN:VCARD
VERSION:3.0
N:{record[last_name]};{record[first_name]};;;
FN:{record[first_name]} {record[last_name]}
REV:2020-07-01T12:00:00Z
UID:{record[id]}
item2.TEL:{record[phone_num]}
item1.EMAIL:{record[email_addr]}
NOTE:Note about {record[first_name]}
item1.X-ABLabel:
item2.X-ABLabel:
END:VCARD
""" \
            .format(record=self) \
            .lstrip()

    def __getitem__(self, item):
        fn = getattr(self, item, None)
        if fn:
            return fn()
        return super().__getitem__(item)


class FakeGoogleApis(GoogleApis):

    def __init__(self, fake_data_repo, cap=None, vcards_allowlist=None):
        self._repo = fake_data_repo
        self._vcards_allowlist = vcards_allowlist

        self.records = self._repo.list().copy()
        if cap is not None:
            self.records = self.records[:cap]

        self.count = len(self.records)

        self._template_env = Environment(
            loader=FileSystemLoader(os.path.join(data_dir_path)),
            autoescape=select_autoescape()
        )
        self._contact_list_template = self._template_env.get_template("contact_list.json.jinja2")
        self._carrdav_report_template = self._template_env.get_template("carddav_report.xml.jinja2")

    def touch_record(self, idx):
        record = self.records[idx]
        new_record = copy.deepcopy(record)
        new_record["rand"] = random.random()  # add element to dict that changes etag hash
        self.records[idx] = new_record
        return new_record

    def change_name(self, idx, first_name, last_name):
        new_record = self.touch_record(idx)
        new_record["first_name"] = first_name
        new_record["last_name"] = last_name
        return new_record

    def allow_vcards(self, hrefs):
        if self._vcards_allowlist is None:
            self._vcards_allowlist = []
        self._vcards_allowlist.extend(hrefs)

    def request_contact_list(self, credentials, page_token=None):
        start = 0
        page_size = 100
        next_page_token = None
        if page_token is not None:
            start = int(page_token)
        end = start + page_size
        if end < len(self.records):
            next_page_token = str(end)

        records_to_render = self.records[start:end]

        resource = self._contact_list_template.render(
            records=records_to_render,
            next_page_token=next_page_token,
            total_people=len(self.records),
            total_items=len(self.records),
        )

        return json.loads(resource)

    def request_carddav_report(self, credentials, principal, request_body):
        ns = {"d": "DAV:", "card": "urn:ietf:params:xml:ns:carddav", }

        hrefs = []
        multiget = ElementTree.fromstring(request_body)
        for href in multiget.findall("d:href", namespaces=ns):
            hrefs.append(href.text)

        records_to_render = [record for record in self.records if record['href'] in hrefs]

        if self._vcards_allowlist is not None:
            for record in records_to_render:
                assert record['href'] in self._vcards_allowlist

        resource = self._carrdav_report_template.render(
            records=records_to_render
        )

        return resource
