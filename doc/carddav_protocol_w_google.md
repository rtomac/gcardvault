# Overview

Gcardvault uses Google's People API to discover contacts, and then Google's CardDAV endpoints for the "last mile" to request VCards.

Technically, you're supposed to use the CardDAV endpoints in a very RESTful manner, starting at a discovery endpoint and then proceeding through a workflow. It was rather difficult to figure out how that all worked in Google's implementation of the spec, so it's documented here for posterity.

# Resources

- [CardDAV spec](https://datatracker.ietf.org/doc/html/rfc6352)
- [Google's CardDAV docs](https://developers.google.com/people/carddav)
- [A useful StackOverflow posting](https://stackoverflow.com/questions/56643565/error-400-invalid-argument-while-requesting-address-book)

# Flow

## Step #1: Discovery endpoint redirect

First, issue a `PROPFIND` on the CardDAV discovery endpoint.

### Request
```
PROPFIND https://www.googleapis.com/.well-known/carddav
Authorization: Bearer ya29.*
```

You will recieve a `301` redirect to the user's default address book.

### Response
```
301 Moved Permanently
Location: /carddav/v1/principals/foo.bar@gmail.com/lists/default/
```

## Step #2: Get contacts from default address book

Next, issue a `PROPFIND` on the default address book (URL we discovered in the first request). The body of the request must be an XML document specifying the properties you're requesting.

Note `Depth` header which indicates that you want the request to return the contacts within the address book, not just properties on the address book itself.

### Request
```
PROPFIND https://www.googleapis.com/carddav/v1/principals/foo.bar@gmail.com/lists/default/
Authorization: Bearer ya29.*
Depth: 1
Content-Type: application/xml; charset=utf-8

<d:propfind xmlns:d="DAV:" xmlns:card="urn:ietf:params:xml:ns:carddav" xmlns:cs="http://calendarserver.org/ns/">
    <d:prop>
        <card:addressbook-description/>
        <d:displayname />
        <d:getetag />
        <d:resourcetype/>
    </d:prop>
</d:propfind>
```

You'll receive a `207` response with an XML doc. The first node contains properties on the address book itself. All subsequent nodes represent contacts within the address book, each with an HREF and an eTag.

### Response
```
207 Multi-Status

<?xml version="1.0" encoding="UTF-8"?>
<d:multistatus xmlns:cal="urn:ietf:params:xml:ns:caldav" xmlns:card="urn:ietf:params:xml:ns:carddav" xmlns:cs="http://calendarserver.org/ns/" xmlns:d="DAV:" xmlns:ical="http://apple.com/ns/ical/">
    <d:response>
        <d:href>/carddav/v1/principals/foo.bar@gmail.com/lists/default/</d:href>
        <d:propstat>
            <d:status>HTTP/1.1 200 OK</d:status>
            <d:prop>
                <d:displayname>Address Book</d:displayname>
                <card:addressbook-description>My Contacts</card:addressbook-description>
                <d:resourcetype>
                    <d:collection/>
                    <card:addressbook/>
                </d:resourcetype>
            </d:prop>
        </d:propstat>
        <d:propstat>
            <d:status>HTTP/1.1 404 Not Found</d:status>
            <d:prop>
                <d:getetag/>
            </d:prop>
        </d:propstat>
    </d:response>
    <d:response>
        <d:href>/carddav/v1/principals/foo.bar@gmail.com/lists/default/10c3c60ceff728</d:href>
        <d:propstat>
            <d:status>HTTP/1.1 200 OK</d:status>
            <d:prop>
                <d:displayname>Contact</d:displayname>
                <d:getetag>"2019-08-15T01:11:22.814-07:00"</d:getetag>
                <d:resourcetype/>
            </d:prop>
        </d:propstat>
        <d:propstat>
            <d:status>HTTP/1.1 404 Not Found</d:status>
            <d:prop>
                <card:addressbook-description/>
            </d:prop>
        </d:propstat>
    </d:response>

    ...

    <d:response>
        <d:href>/carddav/v1/principals/foo.bar@gmail.com/lists/default/7fca66fd0abc9c16</d:href>
        <d:propstat>
            <d:status>HTTP/1.1 200 OK</d:status>
            <d:prop>
                <d:displayname>Contact</d:displayname>
                <d:getetag>"2016-09-12T13:36:53.433-07:00"</d:getetag>
                <d:resourcetype/>
            </d:prop>
        </d:propstat>
        <d:propstat>
            <d:status>HTTP/1.1 404 Not Found</d:status>
            <d:prop>
                <card:addressbook-description/>
            </d:prop>
        </d:propstat>
    </d:response>
</d:multistatus>
```
## Step #3: Get vCards for contacts

Finally, you'll issue a `REPORT` on the same default address book, with an `addressbook-multiget` request in the body. This specifies the contacts you want to return (by HREF) in addition to the properties you want for each of them.

### Request
```
REPORT https://www.googleapis.com/carddav/v1/principals/foo.bar@gmail.com/lists/default/
Authorization: Bearer ya29.*
Content-Type: application/xml; charset=utf-8

<c:addressbook-multiget xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:carddav">
    <d:prop>
        <d:address-data-type />
        <c:address-data />
    </d:prop>
    <d:href>/carddav/v1/principals/foo.bar@gmail.com/lists/default/10c3c60ceff728</d:href>
    ...
    <d:href>/carddav/v1/principals/foo.bar@gmail.com/lists/default/7fca66fd0abc9c16</d:href>
</c:addressbook-multiget>
```

The response will be a `207` containing each contact that was requested. The `card:address-data` nodes contain the vCard content for each.

### Response
```
207 Multi-Status

<?xml version="1.0" encoding="UTF-8"?>
<d:multistatus xmlns:cal="urn:ietf:params:xml:ns:caldav" xmlns:card="urn:ietf:params:xml:ns:carddav" xmlns:cs="http://calendarserver.org/ns/" xmlns:d="DAV:" xmlns:ical="http://apple.com/ns/ical/">
    <d:response>
        <d:href>/carddav/v1/principals/foo.bar@gmail.com/lists/default/10c3c60ceff728</d:href>
        <d:propstat>
            <d:status>HTTP/1.1 200 OK</d:status>
            <d:prop>
                <card:address-data>BEGIN:VCARD
VERSION:3.0
N:Doe;John;;;
FN:John Doe
REV:2021-06-25T21:40:00Z
UID:10c3c60ceff728
TEL;TYPE=CELL:555-555-4577
EMAIL;TYPE=HOME:john.doe@gmail.com
END:VCARD
</card:address-data>
            </d:prop>
        </d:propstat>
        <d:propstat>
            <d:status>HTTP/1.1 404 Not Found</d:status>
            <d:prop>
                <d:address-data-type/>
            </d:prop>
        </d:propstat>
    </d:response>

    ...

    <d:response>
        <d:href>/carddav/v1/principals/foo.bar@gmail.com/lists/default/7fca66fd0abc9c16</d:href>
        <d:propstat>
            <d:status>HTTP/1.1 200 OK</d:status>
            <d:prop>
                <card:address-data>BEGIN:VCARD
VERSION:3.0
N:Doe;Jane;;;
FN:Jane Doe
REV:2021-06-13T06:32:01Z
UID:7fca66fd0abc9c16
ADR;TYPE=HOME:;;12856 SE Main St;Portland;OR;97209;
TEL;TYPE=HOME:(555) 555-0862
TEL;TYPE=CELL:(555) 555-9106
END:VCARD
</card:address-data>
            </d:prop>
        </d:propstat>
        <d:propstat>
            <d:status>HTTP/1.1 404 Not Found</d:status>
            <d:prop>
                <d:address-data-type/>
            </d:prop>
        </d:propstat>
    </d:response>
</d:multistatus>
```
