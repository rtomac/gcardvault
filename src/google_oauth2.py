import os
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials


GOOGLE_AUTH_URI = "https://accounts.google.com/o/oauth2/auth"
GOOGLE_TOKEN_URI = "https://oauth2.googleapis.com/token"
GOOGLE_AUTH_CERTS_URI = "https://www.googleapis.com/oauth2/v1/certs"


class GoogleOAuth2():

    def get_credentials(self, token_file_path, client_id, client_secret, scopes, login_hint):
        credentials = None
        new_authorization = False

        if os.path.exists(token_file_path):
            credentials = Credentials.from_authorized_user_file(token_file_path, scopes)

        if not credentials or not credentials.valid:

            if credentials and credentials.expired and credentials.refresh_token:
                credentials.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_config(
                    {
                        "installed": {
                            "auth_uri": GOOGLE_AUTH_URI,
                            "token_uri": GOOGLE_TOKEN_URI,
                            "auth_provider_x509_cert_url": GOOGLE_AUTH_CERTS_URI,
                            "client_id": client_id,
                            "client_secret": client_secret
                        }
                    },
                    scopes=scopes)
                credentials = flow.run_console(login_hint=login_hint)
                new_authorization = True

            with open(token_file_path, 'w') as token:
                token.write(credentials.to_json())

        return (credentials, new_authorization)

    def request_user_info(self, credentials):
        with build('oauth2', 'v2', credentials=credentials) as service:
            return service.userinfo().get().execute()
