import os
import json
import webbrowser
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials


GOOGLE_AUTH_URI = "https://accounts.google.com/o/oauth2/auth"
GOOGLE_TOKEN_URI = "https://oauth2.googleapis.com/token"
GOOGLE_AUTH_CERTS_URI = "https://www.googleapis.com/oauth2/v1/certs"


class GoogleOAuth2():
    def __init__(self, app_name, authorize_command):
        self.app_name = app_name
        self.authorize_command = authorize_command

    def get_credentials(self, token_file_path, client_id, client_secret, scopes, email_addr):
        credentials = None
        new_authorization = False

        if os.path.exists(token_file_path):
            credentials = Credentials.from_authorized_user_file(token_file_path, scopes)

        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
            self._save_credentials(credentials, token_file_path)
            print(f"Credentials refreshed, token saved to {token_file_path}")
        
        elif not credentials or not credentials.valid:
            credentials = self.authz_and_save_token(token_file_path, client_id, client_secret, scopes, email_addr)
            new_authorization = True

        return (credentials, new_authorization)

    def authz_and_save_token(self, token_file_path, client_id, client_secret, scopes, email_addr):
        if self._check_is_headless():
            print('''
No web browser detected. Google's OAuth2 authorization cannot proceed in headless mode.

On a machine with a web browser, run the following to generate a token and paste it below:
   {authorize_command}

This is a one-time operation. If successful, {app_name} can proceed in headless mode
from this point forward.
''' \
                .format(app_name=self.app_name, authorize_command=self.authorize_command) \
                .format(email_addr=email_addr))
            user_input_token = json.loads(input("Paste the token here:\n").strip())
            credentials = Credentials.from_authorized_user_info(user_input_token)
            self._validate_user_in_token(credentials, email_addr)
            self._save_credentials(credentials, token_file_path)
            print(f"Authorization successful, token saved to {token_file_path}")
        
        else:
            credentials = self._run_authz_flow_and_validate_user(client_id, client_secret, scopes, email_addr)
            self._save_credentials(credentials, token_file_path)
            print(f"Authorization successful, token saved to {token_file_path}")

        return credentials

    def authz_and_export_token(self, client_id, client_secret, scopes, email_addr):
        if self._check_is_headless():
            raise RuntimeError(
                "No web browser detected. Google's OAuth2 authorization cannot proceed in headless mode. "
                "Please run this operation on a machine with a web browser."
            )
        
        else:
            credentials = self._run_authz_flow_and_validate_user(client_id, client_secret, scopes, email_addr)
            print(f'''
Authorization successful, paste the following into your remote machine --->
{credentials.to_json()}
<--- end paste
''')

        return credentials

    def request_user_info(self, credentials):
        with build('oauth2', 'v2', credentials=credentials) as service:
            return service.userinfo().get().execute()

    def _check_is_headless(self):
        #return True
        try:
            webbrowser.get()
            return False
        except webbrowser.Error:
            return True

    def _run_authz_flow_and_validate_user(self, client_id, client_secret, scopes, email_addr):
        flow = InstalledAppFlow.from_client_config(
            {
                'installed': {
                    'auth_uri': GOOGLE_AUTH_URI,
                    'token_uri': GOOGLE_TOKEN_URI,
                    'auth_provider_x509_cert_url': GOOGLE_AUTH_CERTS_URI,
                    'client_id': client_id,
                    'client_secret': client_secret,
                }
            },
            scopes=scopes
        )
        credentials = flow.run_local_server(
            port=0,
            authorization_prompt_message='Please visit this URL: {url}',
            success_message='The auth flow is complete. You may close this window.',
            open_browser=True,
            login_hint=email_addr,
        )
        self._validate_user_in_token(credentials, email_addr)
        return credentials
    
    def _save_credentials(self, credentials, token_file_path):
        with open(token_file_path, 'w') as token:
            token.write(credentials.to_json())
    
    def _validate_user_in_token(self, credentials, email_addr):
        user_info = self.request_user_info(credentials)
        profile_email = user_info['email']
        if email_addr.lower().strip() != profile_email.lower().strip():
            raise ValueError(f"Authenticated user ({profile_email}) was different than the user specified ({email_addr})")
