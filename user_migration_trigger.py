# pyright: reportMissingImports=false, reportMissingModuleSource=false
import os
import json
import logging
from copy import deepcopy
import boto3
import requests

logger = logging.getLogger()
logger.setLevel(logging.INFO)


class AuthApi:

    def __init__(self, secret_id):

        # Fetch secret containing credentials
        sm = boto3.client("secretsmanager")
        response = sm.get_secret_value(SecretId=secret_id)

        # Load value
        secret = json.loads(response["SecretString"])

        # Extract values
        self.domain = secret["domain"]
        self.client_id = secret["client_id"]
        self.client_secret = secret["client_secret"]

    def request(self, method, url, headers, data=None, query=None):
        """
        Makes an HTTP request and returns response details.

        :param method: The HTTP method
        :type method: str
        :param url: The URL to make request to
        :type url: str
        :param headers: Headers to include on request
        :type headers: dict, optional
        :param data: The data object to send, defaults to None
        :type data: dict, optional
        :param query: A dict of query parameters to send, defaults to None
        :type query: dict, optional
        :returns: The response status code and raw response content
        :rtype: int, bytes
        """
        try:
            # Build the request
            response = getattr(requests, method)(url, headers=headers, data=data, params=query)

            # Return response
            return response.status_code, response.content

        except requests.HTTPError as e:
            logger.error(f"Request error: {e.response.status_code} : {e.response.content}")

        except Exception as e:
            logger.exception(f"Error: {e}", exc_info=True)

    def check_credentials(self, username, password):
        """
        Checks Auth API for the given username and password.

        :param username: The entered username/email
        :type username: str
        :param password: The entered password
        :type password: str
        :returns: Whether the credentials are valid or not
        :rtype: boolean
        """
        try:
            # Set request details
            url = f"https://{self.domain}/oauth/token"
            headers = {"Content-Type": "application/x-www-form-urlencoded"}
            data = {
                "grant_type": "password",
                "username": username,
                "password": password,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            }

            # Make the request
            status_code, _ = self.request("POST", url, headers=headers, data=data)

            # Auth API returns 200 if login was successful
            return status_code == 200

        except requests.HTTPError as e:
            logger.error(f"Check credentials request error: {e.response.status_code} : {e.response.content}")

        except Exception as e:
            logger.exception(f"Error: {e}", exc_info=True)

        raise SystemError("Failed to check login for user")

    def get_management_api_token(self):
        """
        Fetches and returns an Auth0 management API token. This is the
        only API able to query users to check for their existence in Auth0.

        :raises SystemError: Process cannot recover if token cannot be fetched
        :returns: The token to authentication management API requests
        :rtype: str
        """
        try:
            # Set request details for getting a management API token
            url = f"https://{self.domain}/oauth/token"
            headers = {"Content-Type": "application/x-www-form-urlencoded"}
            data = {
                "grant_type": "client_credentials",
                "audience": f"https://{self.domain}/api/v2/",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            }

            # Make the request
            _, content = self.request("POST", url, headers=headers, data=data)

            # Load JSON
            response = json.loads(content)

            # Get the management API token
            return response["access_token"]

        except Exception as e:
            logger.exception(f"Error: {e}", exc_info=True)

        raise SystemError("Could not retrieve Auth0 management API token")

    def check_username(self, username):
        """
        Checks Auth API for the entered username.

        :param username: The entered username/email
        :type username: str
        :raises SystemError: Process cannot recover if username check fails
        :returns: Whether the user exists or not
        :rtype: boolean
        """
        # Get the token
        token = self.get_management_api_token()

        try:
            # Set request details
            url = f"https://{self.domain}/api/v2/users-by-email"
            headers = {
                "Authorization": f"Bearer {token}"
            }
            params = {
                "email": username,
            }

            # Make the request
            _, content = self.request("GET", url, headers=headers, query=params)

            # Load JSON
            users = json.loads(content)
            if not users:
                logger.info(f"No user found for username '{username}'")
                return False

            # Ensure the user is using username and password identity
            user = next(iter(users))
            is_username_and_password = next(
                (i for i in user["identities"] if i["connection"] == "Username-Password-Authentication"),
                False
            )

            # No need to migrate SSO users
            if not is_username_and_password:
                logger.info(f"User '{username}' was found but does not use Username-Password-Authentication")
                return False

            return True

        except requests.HTTPError as e:
            logger.error(f"Username check request error: {e.response.status_code} : {e.response.content}")

        except Exception as e:
            logger.exception(f"Error: {e}", exc_info=True)

        raise SystemError("Failed to check for existence of user")


def lambda_handler(event, context):

    # Log the event with password scrubbed
    event_output = deepcopy(event)
    event_output["request"].setdefault("password", "********")
    logger.info(f"Event: {event_output}")

    # Get secret ID from environment
    secret_id = os.environ["AUTH_API_CREDENTIALS_SECRET_ID"]

    # Initialize API
    api = AuthApi(secret_id)

    # Get username and password
    username = event["userName"]
    password = event["request"].get("password")

    # If a new Cognito user attempts to login and Cognito determines their
    # username is invalid, we are given the opportunity here to check with
    # the auth provider we are migrating from to seamlessly migrate their
    # account without interruption. Requires their submitted username and
    # password are valid. If the check succeeds, the user is added to the
    # Cognito database with their current password and the current as well
    # as future logins will succeed normally.
    if event["triggerSource"] == "UserMigration_Authentication":

        # Check if user is valid
        if api.check_credentials(username, password):
            logger.info(f"User '{username}' was successfully authenticated with Auth0")

            # Confirm the user
            event["response"]["finalUserStatus"] = "CONFIRMED"
            event["response"]["messageAction"] = "SUPPRESS"
            event["response"]["userAttributes"] = {
                "email": username,
            }

        else:
            logger.info(f"User '{username}' failed to authenticate with Auth0")
            raise Exception(f"username and/or password are invalid")

    # If a new Cognito user wants to reset their password but does not yet
    # exist in Cognito, we check our previous auth provider to ensure they
    # had an account for the email submitted. If the check succeeds,
    # we add them to the Cognito database and mark their email as confirmed and
    # Cognito starts the process of letting them "reset" their password via
    # via email.
    elif event["triggerSource"] == "UserMigration_ForgotPassword":

        # Check if user is valid
        if api.check_username(username):
            logger.info(f"User '{username}' exists in Auth0")

            # We have to mark email as verified so Cognito can process
            # password recovery via email
            event["response"]["userAttributes"] = {
                "email": username,
                "email_verified": True,
            }
            event["response"]["messageAction"] = "SUPPRESS"

        else:
            logger.info(f"User '{username}' does not exist in Auth0")
            raise Exception(f"no user found for username '{username}'")

    else:
        raise NotImplementedError(f"Unhandled trigger source '{event['triggerSource']}'")


    logger.info(f"Response: {event['response']}")
    return event
