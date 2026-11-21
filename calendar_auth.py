import os
import pickle
import datetime
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

SCOPES = ['https://www.googleapis.com/auth/calendar']
def get_calendar_service():
    creds = None
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    
    has_calendar_scopes = creds is not None and creds.has_scopes(SCOPES)
    if not creds or not creds.valid or not has_calendar_scopes:
        if creds and creds.expired and creds.refresh_token and has_calendar_scopes:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        
        # Save the credentials for future use
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)
    
    return creds

def main():
    get_calendar_service()

if __name__ == '__main__':
    main()