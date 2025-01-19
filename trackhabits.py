import requests
import google_auth_oauthlib
import webbrowser
import threading
import math
import pytz
import google.oauth2.credentials
import google.auth.transport.requests
import pprint

from datetime import *
from googleapiclient.discovery import build
from flask import Flask, request, url_for, redirect
from apscheduler.schedulers.background import BackgroundScheduler

SHEET_RANGE = '' 
SHEET_ID = ''
sheets = None
rows = None

strava_access_token = ''
strava_expires_at = 0
strava_refresh_token = ''

GOOGLE_CLIENT_ID = ''
GOOGLE_CLIENT_SECRET = ''

STRAVA_AUTH_URL = 'https://www.strava.com/oauth/authorize'
STRAVA_TOKEN_URL = 'https://www.strava.com/api/v3/oauth/token'
STRAVA_SCOPE = 'activity:read'
STRAVA_CLIENT_ID = 0
STRAVA_CLIENT_SECRET = ''
STRAVA_ACTIVITIES_URL = 'https://www.strava.com/api/v3/athlete/activities'

HEVY_API_KEY = ''
HEVY_WORKOUTS_URL = 'https://api.hevyapp.com/v1/workouts'

REDIRECT_URI = 'http://localhost:8080/callback'

app = Flask(__name__)

# user is redirected here after the strava oauth consent screen. this is called exactly once.
@app.route('/callback')
def callback():
    global strava_access_token
    global strava_refresh_token
    global strava_expires_at
    
    code = request.args.get('code')
    
    if code:
        token_response = exchange_code_for_token(code)
        strava_access_token = token_response['access_token']
        strava_refresh_token = token_response['refresh_token']
        strava_expires_at = token_response['expires_at']
        print(f'Strava token obtained: {token_response}')
    else:
        raise Exception('Error: No code in the request.')
    
    return redirect(url_for('resume_control'))

# resume control to core logic after authenticating strava user, begin schedule after operation succeeds. this is called exactly once.
@app.route('/')
def resume_control():
    update_rows_with_runs(rows)
    update_rows_with_lifts(rows)
    update_google_sheet(rows)
    print('\n initial run succeeded, sheet updated... \n')
    return redirect(url_for('schedule'))

@app.route('/schedule')
def schedule():
    start_scheduler()
    return 'Updating sheet with new strava runs and hevy workouts every 5 minutes...'

def authenticate_sheets(credentials):
    return build('sheets', 'v4', discoveryServiceUrl='https://sheets.googleapis.com/$discovery/rest?version=v4',credentials=credentials).spreadsheets()

def get_col_idx(header_row, header: str):
    for i in range(0, len(header_row)):
        if header_row[i] == header:
            return i
    raise Exception(f'No {header} header found')

def refresh_strava_token(client_id: int, client_secret: str):
    global strava_refresh_token
    global strava_access_token
    global strava_expires_at
    
    params = {
        'client_id': client_id,
        'client_secret': client_secret,
        'grant_type': 'refresh_token',
        'refresh_token': strava_refresh_token
    }

    resp = requests.post(STRAVA_TOKEN_URL, params=params)

    if resp.status_code >= 400:
         raise Exception('the request made to refresh the access token failed')
    elif resp.status_code > 200:
         raise Exception(f'unexpected response when refreshing access token with:\nstatus code: {resp.status_code}\nheaders: {resp.headers}\nbody: {resp.json()}')
    else:
         body = resp.json()
         print(body)
         strava_refresh_token = body['refresh_token']
         strava_access_token = body['access_token']
         strava_expires_at = int(body['expires_at'])

    print('access token refreshed successfully.')
      
def get_activities_from_strava() -> list:
    epoch_first_logged_date = 1725840000

    params = {
          'after' : epoch_first_logged_date,
          'per_page' : 200,
          'page': 1
    }
    
    headers = {
        'Authorization': f'Bearer {strava_access_token}'
    }

    activities = []

    while True:
        if strava_access_token == '':
            auth_url = f'{STRAVA_AUTH_URL}?response_type=code&client_id={STRAVA_CLIENT_ID}&redirect_uri={REDIRECT_URI}&scope={STRAVA_SCOPE}'
            webbrowser.open(auth_url)
            while True: 
                # infinite loop to keep main thread from shutting down so that BackgroundScheduler can register thread shutdown functions
                pass
        if strava_expires_at < int(datetime.now().timestamp()):
            print('strava access token is stale, refreshing...')
            refresh_strava_token(STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET)
            headers['Authorization'] = f'Bearer {strava_access_token}'
        
        resp = requests.get(STRAVA_ACTIVITIES_URL, params=params, headers=headers)
        
        if resp.status_code != 200:
            raise Exception(f"strava activities api responded in an unexpected fashion:\nstatus code: {resp.status_code}\nheaders: {resp.headers}\nbody: {resp.json()}")
        
        if len(resp.json()) == 0: 
            break
        else:
            activities.extend(resp.json())   
            params['page'] = params['page'] + 1 

    return activities

def update_rows_with_runs(rows: list):
    cardio_col_idx = get_col_idx(rows[0], 'Cardio')
    miles_ran_col_idx = get_col_idx(rows[0], 'Miles')
    pace_col_idx = get_col_idx(rows[0], 'Pace')
    time_col_idx = get_col_idx(rows[0], 'Time')
    activities = get_activities_from_strava()
    
    for activity in activities: 
        for i in range(1, len(rows)):
            if datetime.strptime(rows[i][0], "%m/%d/%Y").date() == datetime.fromisoformat(activity['start_date_local']).date():
                rows[i][cardio_col_idx] = True
                rows[i][miles_ran_col_idx] = round(activity['distance'] * 0.000621371, 2) # converts meters to miles
                rows[i][pace_col_idx] = get_as_mins_and_secs(60 / (activity['average_speed'] * 2.2369356)) + '/mi' # converts meters/sec to minutes per miles
                rows[i][time_col_idx] = get_as_mins_and_secs(activity['moving_time'] / 60) # converts seconds to minutes and seconds
                break
            
def update_rows_with_lifts(rows: list):
    lift_col_idx = get_col_idx(rows[0], 'Lift')
    workouts  = get_workouts_from_hevy()

    for workout in workouts: 
        for i in range(1, len(rows)):
            if datetime.strptime(rows[i][0], "%m/%d/%Y").date() == get_local_time(workout['start_time']):
                rows[i][lift_col_idx] = True
                break
    
            
def get_workouts_from_hevy() -> list:
    workouts = []
    pg = 1

    while True: 
        resp = requests.get(HEVY_WORKOUTS_URL, headers={'api-key': HEVY_API_KEY}, params={'page': pg, 'pageSize': 10})
        
        if resp.status_code != 200:
            raise Exception(f"hevy workouts api responded in an unexpected fashion:\nstatus code: {resp.status_code}\nheaders: {resp.headers}\nbody: {resp.json()}")
        
        workouts.extend(resp.json()['workouts'])
        
        if (pg == resp.json()['page_count']):
            break
        
        pg += 1
        
    return workouts
    
def get_local_time(utc_str: str):
    utc_time = datetime.fromisoformat(utc_str)
    est = pytz.timezone("US/Eastern")
    return utc_time.astimezone(est).date()
    

def update_google_sheet(rows: list):
    body = {
        'majorDimension' : 'ROWS',
        'range': SHEET_RANGE,
        'values': rows
    }
    
    obj = sheets.values().update(spreadsheetId=SHEET_ID, range=SHEET_RANGE, valueInputOption='USER_ENTERED', body=body).execute()
    
    # print(f'\n{obj}\n')
    
def get_google_credentials() -> google.oauth2.credentials.Credentials: 
    scopes = ['https://www.googleapis.com/auth/spreadsheets']
    credentials = google_auth_oauthlib.get_user_credentials(scopes, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET)
    
    print(f'\ngoogle credentials')
    pprint.pprint(vars(credentials))
    
    return credentials

# sheets api removes trailing empty cells in each record
def fill_ragged_2d_array(rows: list):
    for i in range(1, len(rows)):
        if len(rows[i]) < len(rows[0]):
            rows[i].extend((len(rows[0]) - len(rows[i])) * [''])
            
def get_as_mins_and_secs(mins: float) -> str:
    min = math.floor(mins)
    sec = round((mins - min) * 60)
    return f'{min}:{sec:02}'

def exchange_code_for_token(code):
    payload = {
        'grant_type': 'authorization_code',
        'code': code,
        'client_id': STRAVA_CLIENT_ID,
        'client_secret': STRAVA_CLIENT_SECRET,
    }
    response = requests.post(STRAVA_TOKEN_URL, data=payload)
    return response.json()

def main():
    global rows 
    global sheets
    global google_credentials
    
    if (google_credentials.expiry < datetime.now()):
        print('\ngoogle_credentials expired, refreshing...\n')
        request = google.auth.transport.requests.Request()
        google_credentials.refresh(request)
    
    sheets = authenticate_sheets(google_credentials)
    rows = sheets.values().get(spreadsheetId=SHEET_ID, range=SHEET_RANGE).execute()['values']
    fill_ragged_2d_array(rows)
    update_rows_with_runs(rows)
    update_rows_with_lifts(rows)
    update_google_sheet(rows)
    print('sheet updated...')

def run_app():
    app.run(port=8080, use_reloader=False)  # Disable reloader if running in threads
    
# Start the scheduler to run in the background
def start_scheduler():
    scheduler = BackgroundScheduler()
    scheduler.add_job(main, 'interval', minutes=1)  # Run every 5 minutes
    scheduler.start()

google_credentials = get_google_credentials()

if __name__ == '__main__':
    thread = threading.Thread(target=run_app)
    thread.start()

main()