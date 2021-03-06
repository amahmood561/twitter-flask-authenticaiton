import os
from flask import Flask, render_template, redirect, request, url_for, jsonify
import oauth2 as oauth
import urllib.request
import urllib.parse
import urllib.error
import json
import jwt
from flask_cors import CORS, cross_origin
import http.client

app = Flask(__name__)

app.debug = False
cors = CORS(app)
app.config['CORS_HEADERS'] = 'Content-Type'

request_token_url = 'https://api.twitter.com/oauth/request_token'
access_token_url = 'https://api.twitter.com/oauth/access_token'
authorize_url = 'https://api.twitter.com/oauth/authorize'
show_user_url = 'https://api.twitter.com/1.1/users/show.json'
dashboard_overview = 'http://localhost:3000/#/dashboard/overview'

# Support keys from environment vars (Heroku).
app.config['APP_CONSUMER_KEY'] = os.getenv(
    'TWAUTH_APP_CONSUMER_KEY', 'API_Key_from_Twitter')
app.config['APP_CONSUMER_SECRET'] = os.getenv(
    'TWAUTH_APP_CONSUMER_SECRET', 'API_Secret_from_Twitter')

# alternatively, add your key and secret to config.cfg
# config.cfg should look like:
APP_CONSUMER_KEY = ''
APP_CONSUMER_SECRET = ''
app.config.from_pyfile('config.cfg', silent=True)

oauth_store = {}


@app.route('/')
def hello():
    return render_template('index.html')


@app.route('/start')
@cross_origin()
def start():
    # note that the external callback URL must be added to the whitelist on
    # the developer.twitter.com portal, inside the app settings
    app_callback_url = url_for('callback', _external=True)

    # Generate the OAuth request tokens, then display them
    consumer = oauth.Consumer(
        app.config['APP_CONSUMER_KEY'], app.config['APP_CONSUMER_SECRET'])
    client = oauth.Client(consumer)
    resp, content = client.request(request_token_url, "POST", body=urllib.parse.urlencode({
        "oauth_callback": app_callback_url}))

    if resp['status'] != '200':
        error_message = 'Invalid response, status {status}, {message}'.format(
            status=resp['status'], message=content.decode('utf-8'))
        return render_template('error.html', error_message=error_message)

    request_token = dict(urllib.parse.parse_qsl(content))
    oauth_token = request_token[b'oauth_token'].decode('utf-8')
    oauth_token_secret = request_token[b'oauth_token_secret'].decode('utf-8')

    oauth_store[oauth_token] = oauth_token_secret
    return render_template('start.html', authorize_url=authorize_url, oauth_token=oauth_token,
                           request_token_url=request_token_url)


def getBearerTokenForV2():
    import http.client
    conn = http.client.HTTPSConnection("api.twitter.com")
    payload = ''
    headers = {
        'Authorization': 'Basic b3ZvR09kYnVYUGMxQ3FSOTI2TnJyc2UzRTpCQ2JFamJPRG9VQllDZ2RxMWZMTzM0cm5rNzJ3cWdPYjJ3MHF3dmdxNE1HSnRnRDRGVQ=='
    }
    conn.request("POST", "/oauth2/token?grant_type=client_credentials", payload, headers)
    res = conn.getresponse()
    data = res.read()
    print(data.decode("utf-8"))
    return data.decode("utf-8")


@app.route('/callback')
@cross_origin()
def callback():
    # Accept the callback params, get the token and call the API to
    # display the logged-in user's name and handle
    oauth_token = request.args.get('oauth_token')
    oauth_verifier = request.args.get('oauth_verifier')
    oauth_denied = request.args.get('denied')

    # if the OAuth request was denied, delete our local token
    # and show an error message
    if oauth_denied:
        if oauth_denied in oauth_store:
            del oauth_store[oauth_denied]
        return render_template('error.html', error_message="the OAuth request was denied by this user")

    if not oauth_token or not oauth_verifier:
        return render_template('error.html', error_message="callback param(s) missing")

    # unless oauth_token is still stored locally, return error
    if oauth_token not in oauth_store:
        return render_template('error.html', error_message="oauth_token not found locally")

    oauth_token_secret = oauth_store[oauth_token]

    # if we got this far, we have both callback params and we have
    # found this token locally

    consumer = oauth.Consumer(
        app.config['APP_CONSUMER_KEY'], app.config['APP_CONSUMER_SECRET'])
    token = oauth.Token(oauth_token, oauth_token_secret)
    token.set_verifier(oauth_verifier)
    client = oauth.Client(consumer, token)

    resp, content = client.request(access_token_url, "POST")
    access_token = dict(urllib.parse.parse_qsl(content))

    screen_name = access_token[b'screen_name'].decode('utf-8')
    user_id = access_token[b'user_id'].decode('utf-8')

    # These are the tokens you would store long term, someplace safe
    real_oauth_token = access_token[b'oauth_token'].decode('utf-8')
    real_oauth_token_secret = access_token[b'oauth_token_secret'].decode(
        'utf-8')

    # Call api.twitter.com/1.1/users/show.json?user_id={user_id}
    real_token = oauth.Token(real_oauth_token, real_oauth_token_secret)
    real_client = oauth.Client(consumer, real_token)
    real_resp, real_content = real_client.request(
        show_user_url + '?user_id=' + user_id, "GET")
    print(real_resp['content-location'])
    v2_verification = getBearerTokenForV2()
    encoded = jwt.encode(
        {'key': real_oauth_token, 'secret': real_oauth_token_secret, 'user_id': user_id, 'v2Token': v2_verification},
        'secret', algorithm='HS256')

    decodedjwt = jwt.decode(encoded, 'secret', algorithms=['HS256'])

    # if real_resp['status'] != '200':
    #    error_message = "Invalid response from Twitter API GET users/show: {status}".format(
    #        status=real_resp['status'])
    #    return render_template('error.html', error_message=error_message)

    # response = json.loads(real_content.decode('utf-8'))

    # response = redirect(url_for(dashboard_overview))
    # response.headers['X-JWT-TOKEN'] = encoded
    # response = redirect(dashboard_overview+'/?token='+ encoded ,code=200)
    # response.headers['Access-Control-Allow-Origin'] = '*'
    # response.headers['X-JWT-TOKEN'] = encoded
    response = redirect(dashboard_overview + '?token=' + encoded)
    response.headers['X-JWT-TOKEN'] = encoded
    return response


@app.route('/DashBoardInfoApi1', methods=['POST'])
@cross_origin()
def GetDashBoardInfoApi1():
    request_json = request.get_json()
    token = request_json.get('tokenEncoded')
    decodedjwt = jwt.decode(token, 'secret', algorithms=['HS256'])
    v2TokenLoaded = res = json.loads(decodedjwt['v2Token'])['access_token']
    user_id = decodedjwt['user_id']
    userInfoById = getUserByID(v2TokenLoaded, user_id)
    userDataLoaded = userInfoById['data']
    UserByScreenName = getUserByScreenName(v2TokenLoaded, userDataLoaded[0]['username'])
    UserTweetsById = getUserTweets(v2TokenLoaded, user_id)
    finalResponseDict = {'ById': userInfoById, 'BySN': UserByScreenName, 'UserTweets': UserTweetsById}
    return finalResponseDict


def getUserTweets(token, id):
    conn = http.client.HTTPSConnection("api.twitter.com")
    payload = ''
    headers = {
        'Authorization': 'Bearer ' + token,
        'Cookie': 'guest_id=v1%3A162137747958631578; guest_id_ads=v1%3A162137747958631578; guest_id_marketing=v1%3A162137747958631578; personalization_id="v1_lg8zB7oNfzevckwqkebfYw=="'
    }
    conn.request("GET", "/2/users/" + id + "/tweets", payload, headers)
    res = conn.getresponse()
    data = res.read()
    frmted = json.loads(data.decode("utf-8"))

    return frmted


def getUserByID(token, id):
    conn = http.client.HTTPSConnection("api.twitter.com")
    payload = ''
    headers = {
        'Authorization': 'Bearer ' + token,
        'Cookie': 'guest_id=v1%3A162137747958631578; guest_id_ads=v1%3A162137747958631578; guest_id_marketing=v1%3A162137747958631578; personalization_id="v1_lg8zB7oNfzevckwqkebfYw=="'
    }
    conn.request("GET",
                 "/2/users?ids=" + id + "&user.fields=created_at,description,entities,id,location,name,pinned_tweet_id,profile_image_url,protected,url,username,verified,withheld&expansions=pinned_tweet_id",
                 payload, headers)
    res = conn.getresponse()
    data = res.read()
    print(data.decode("utf-8"))
    frmted = json.loads(data.decode("utf-8"))

    return frmted


def getUserByScreenName(token, screenName):
    conn = http.client.HTTPSConnection("api.twitter.com")
    payload = ''
    headers = {
        'Authorization': 'Bearer ' + token,
        'Cookie': 'guest_id=v1%3A162137747958631578; guest_id_ads=v1%3A162137747958631578; guest_id_marketing=v1%3A162137747958631578; personalization_id="v1_lg8zB7oNfzevckwqkebfYw=="'
    }
    conn.request("GET", "/1.1/users/show.json?screen_name=" + screenName, payload, headers)
    res = conn.getresponse()
    data = res.read()
    print(data.decode("utf-8"))
    frmted = json.loads(data.decode("utf-8"))

    return frmted


@app.route('/DashBoardInfoApi', methods=['POST'])
@cross_origin()
def GetDashBoardInfoApi():
    # set request context type to json on post
    request_json = request.get_json()
    token = request_json.get('tokenEncoded')
    decodedjwt = jwt.decode(token, 'secret', algorithms=['HS256'])
    # Accept the callback params, get the token and call the API to
    # display the logged-in user's name and handle
    oauth_token = request.args.get('oauth_token')
    oauth_verifier = request.args.get('oauth_verifier')
    oauth_denied = request.args.get('denied')

    oauth_token_secret = oauth_store[oauth_token]

    # if we got this far, we have both callback params and we have
    # found this token locally

    consumer = oauth.Consumer(
        app.config['APP_CONSUMER_KEY'], app.config['APP_CONSUMER_SECRET'])
    token = oauth.Token(oauth_token, oauth_token_secret)
    token.set_verifier(oauth_verifier)
    client = oauth.Client(consumer, token)

    resp, content = client.request(access_token_url, "POST")
    access_token = dict(urllib.parse.parse_qsl(content))

    screen_name = access_token[b'screen_name'].decode('utf-8')

    # These are the tokens you would store long term, someplace safe
    real_oauth_token = access_token[b'oauth_token'].decode('utf-8')
    real_oauth_token_secret = access_token[b'oauth_token_secret'].decode(
        'utf-8')

    # Call api.twitter.com/1.1/users/show.json?user_id={user_id}
    real_token = oauth.Token(real_oauth_token, real_oauth_token_secret)
    real_client = oauth.Client(consumer, real_token)
    real_resp, real_content = real_client.request(
        show_user_url + '?user_id=' + user_id, "GET")

    encoded = jwt.encode({'key': real_oauth_token, 'secret': real_oauth_token_secret}, 'secret', algorithm='HS256')

    decodedjwt = jwt.decode(encoded, 'secret', algorithms=['HS256'])

    if real_resp['status'] != '200':
        error_message = "Invalid response from Twitter API GET users/show: {status}".format(
            status=real_resp['status'])
        return render_template('error.html', error_message=error_message)

    response = json.loads(real_content.decode('utf-8'))

    friends_count = response['friends_count']
    statuses_count = response['statuses_count']
    followers_count = response['followers_count']
    name = response['name']
    # don't keep this token and secret in memory any longer
    del oauth_store[oauth_token]

    return {'friendsCount': friends_count, 'statusesCcount': statuses_count, 'followersCount': followers_count}


@app.route('/callbackOriginal')
@cross_origin()
def callbackOriginal():
    # Accept the callback params, get the token and call the API to
    # display the logged-in user's name and handle
    oauth_token = request.args.get('oauth_token')
    oauth_verifier = request.args.get('oauth_verifier')
    oauth_denied = request.args.get('denied')

    # if the OAuth request was denied, delete our local token
    # and show an error message
    if oauth_denied:
        if oauth_denied in oauth_store:
            del oauth_store[oauth_denied]
        return render_template('error.html', error_message="the OAuth request was denied by this user")

    if not oauth_token or not oauth_verifier:
        return render_template('error.html', error_message="callback param(s) missing")

    # unless oauth_token is still stored locally, return error
    if oauth_token not in oauth_store:
        return render_template('error.html', error_message="oauth_token not found locally")

    oauth_token_secret = oauth_store[oauth_token]

    # if we got this far, we have both callback params and we have
    # found this token locally

    consumer = oauth.Consumer(
        app.config['APP_CONSUMER_KEY'], app.config['APP_CONSUMER_SECRET'])
    token = oauth.Token(oauth_token, oauth_token_secret)
    token.set_verifier(oauth_verifier)
    client = oauth.Client(consumer, token)

    resp, content = client.request(access_token_url, "POST")
    access_token = dict(urllib.parse.parse_qsl(content))

    screen_name = access_token[b'screen_name'].decode('utf-8')
    user_id = access_token[b'user_id'].decode('utf-8')

    # These are the tokens you would store long term, someplace safe
    real_oauth_token = access_token[b'oauth_token'].decode('utf-8')
    real_oauth_token_secret = access_token[b'oauth_token_secret'].decode(
        'utf-8')

    # Call api.twitter.com/1.1/users/show.json?user_id={user_id}
    real_token = oauth.Token(real_oauth_token, real_oauth_token_secret)
    real_client = oauth.Client(consumer, real_token)
    real_resp, real_content = real_client.request(
        show_user_url + '?user_id=' + user_id, "GET")

    encoded = jwt.encode({'key': real_oauth_token, 'secret': real_oauth_token_secret}, 'secret', algorithm='HS256')

    decodedjwt = jwt.decode(encoded, 'secret', algorithms=['HS256'])

    if real_resp['status'] != '200':
        error_message = "Invalid response from Twitter API GET users/show: {status}".format(
            status=real_resp['status'])
        return render_template('error.html', error_message=error_message)

    response = json.loads(real_content.decode('utf-8'))

    friends_count = response['friends_count']
    statuses_count = response['statuses_count']
    followers_count = response['followers_count']
    name = response['name']
    # don't keep this token and secret in memory any longer
    del oauth_store[oauth_token]
    return render_template('callback-success.html', encoded_jwt=encoded, decoded_jwt=decodedjwt,
                           screen_name=screen_name, user_id=user_id, name=name,
                           friends_count=friends_count, statuses_count=statuses_count, followers_count=followers_count,
                           access_token_url=access_token_url)


@app.errorhandler(500)
@cross_origin()
def internal_server_error(e):
    return render_template('error.html', error_message='uncaught exception'), 500


if __name__ == '__main__':
    app.run()
