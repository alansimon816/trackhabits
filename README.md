README.md

<u>Description</u>

- This program updates a personal Google Sheet that has an assumed format. Some assumptions are explicitly made via the invocations on the get_col_idx function in the script. The sheet is assumed to have 365 rows, for 365 days in a year. The first row in the sheet is assumed to contain text cells that serve as labels for their respective columns. The app first sends the user to Google sign-in page, then requests permissions to view/edit their sheet associated with the specified id. If the user consents, then the app authenticates to the sheets API resource using the user credentials. Then, the sheet data is pulled via google client libraries. The app then initiates a Strava OAuth flow using client credentials, which involves requesting user consent, followed by an authorization code being supplied to the app as a query parameter sent in a GET request to a configured redirect URI. The code is exchanged by the app for an access token and refresh token, to be re-used for all subsequent requests to the list Strava user activities API. Activities are retrieved from Strava for the user, and the relevant sheet cells matching the dates of the strava activities are updated accordingly. Metrics such as avg. mile pace, total running time, and total miles are recorded. After that, the app pings the Hevy App API (only available for Hevy Pro users) for logged workouts and simply checks off a checkbox in the 'Lift' cell in the row for the sheet in which the date matches the date of the workout being referenced. After the initial run, the program runs indefinitely, operating on a schedule that repeats the core functionality every 5 minutes, re-using previously captured information such as auth tokens, such that no further manual user action is required. The app is multi-threaded. A flask dev server is ran in a child thread to facilitate the strava oauth callback, resuming core logic and storing the refresh token, access token, and expiry as global variables in the child thread. The main thread is left to run indefinitely in an infinite while loop to support the intention of this app being ran indefinitely as a background process or daemon on the host machine. The infinite loop also permits the schedule to configure shutdown tasks on threads it spins up in anticipation of manual program exit, without error.

<b>TL;DR</b>

A daemon that updates an annual google sheet that is personalized to log strava runs and hevy workouts, every 5 minutes. 

<u>Instructions</u>
1. Create a Google Sheet containing the assumed headers in row 0
2. Fill Column A with mm/dd/yy dates using fill tool
3 Fill column B with Day of week using fill tool
4. Set SHEET_RANGE global variable to the name of the sheet within the spreadsheet
5. Assign the appropriate values to the GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, SHEET_ID, STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET, HEVY_API_KEY global variables.
6. start script from CLI (ie python3 trackhabits.py)


<u>Notes</u>

- Strava API has a 1000 requests per day, 100 requests per 15 minutes rate limit on all "non-upload" apis, which includes the GET athlete activities api that this script pings

- Hevy API does not explicitly cite an API rate limit, so we conservatively opt for making a request to both Hevy and Strava APIs every 5 minutes.

- At the beginning of a new year, use fill tool in Sheets UI to add the next 365 cells to previous sheet's year, then duplicate the sheet, then remove previous year's rows from the new sheet, then remove new rows from old, then update sheet_range in script to reflect the new year.

- Uses port 8080 on localhost


<u>Future Upgrades</u>
- Exponential Backoff when making requests to third party APIs
- Handle Hevy specific errors
- # requests.exceptions.SSLError: HTTPSConnectionPool(host='api.hevyapp.com', port=443): Max retries exceeded with url: /v1/workouts?page=39&pageSize=10 (Caused by SSLError(SSLEOFError(8, '[SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in violation of protocol (_ssl.c:1018)')))
- # requests.exceptions.ConnectionError: HTTPSConnectionPool(host='api.hevyapp.com', port=443): Max retries exceeded with url: /v1/workouts?page=22&pageSize=10 (Caused by NameResolutionError("<urllib3.connection.HTTPSConnection object at 0x108d51590>: Failed to resolve 'api.hevyapp.com' ([Errno 8] nodename nor servname provided, or not known)"))
